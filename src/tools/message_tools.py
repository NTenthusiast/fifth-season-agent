"""「第五季」留言信箱工具（v7.0）

用户可通过知颜向其他用户留言，便于项目匹配后建立联系：
- send_message：把话投递到对方信箱
- check_my_inbox：查看自己的信箱（未读优先，读后自动标记已读）

数据表：fs_messages(sender_id, receiver_id, content, is_read, created_at)
"""

from langchain.tools import tool
from postgrest.exceptions import APIError

from storage.database.supabase_client import get_supabase_client
from tools.db_helpers import (
    err_str,
    find_user_by_nickname,
    get_user_id,
    result_str,
    rows_of,
)


@tool
def send_message(from_nickname: str, to_nickname: str, content: str) -> str:
    """通过知颜向其他用户留言（投递到对方信箱）。用于匹配到合适的前辈/接棒人后主动建立联系。
    from_nickname 必须是当前登录用户本人的昵称（系统已注入登录身份，严禁冒充他人发送）。

    Args:
        from_nickname: 发送者昵称（必须是当前登录用户本人）
        to_nickname: 接收者昵称（需已注册）
        content: 留言内容，100 字以内，语气友好，说明来意（如想交流的项目方向、自己的情况）
    """
    from_nickname = (from_nickname or "").strip()
    to_nickname = (to_nickname or "").strip()
    content = (content or "").strip()
    if not from_nickname or not to_nickname:
        return err_str("发送者与接收者昵称均不能为空")
    if from_nickname == to_nickname:
        return err_str("不能给自己留言")
    if not content or len(content) > 500:
        return err_str("留言内容必填，且不超过 500 字")

    try:
        sender = find_user_by_nickname(from_nickname)
        if sender is None:
            return err_str(f"发送者「{from_nickname}」尚未注册，无法以该身份留言")
        receiver = find_user_by_nickname(to_nickname)
        if receiver is None:
            return err_str(f"收件人「{to_nickname}」不存在，请确认对方昵称（可先用 find_users_by_tags / find_mentors 检索确认）")

        client = get_supabase_client()
        resp = client.table("fs_messages").insert({
            "sender_id": int(sender["id"]),
            "receiver_id": int(receiver["id"]),
            "content": content,
        }).execute()
        row = (rows_of(resp) or [{}])[0]
        return result_str({
            "success": True,
            "action": "send_message",
            "message_id": row.get("id"),
            "to": to_nickname,
            "message": f"留言已投递到「{to_nickname}」的信箱，对方下次进入网页时会看到未读提醒。",
        })
    except APIError as e:
        return err_str(f"留言投递失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(f"留言投递失败: {e}")


@tool
def check_my_inbox(nickname: str) -> str:
    """查看自己的留言信箱：谁给我留了言、内容是什么。用户说"看看我的信箱/有没有人给我留言"时调用。
    查看后未读留言自动标记为已读。

    Args:
        nickname: 当前用户昵称
    """
    nickname = (nickname or "").strip()
    if not nickname:
        return err_str("昵称不能为空")
    try:
        uid = get_user_id(nickname)
        if uid is None:
            return err_str(f"「{nickname}」尚未注册")

        client = get_supabase_client()
        rows = rows_of(
            client.table("fs_messages")
            .select("id, sender_id, content, is_read, created_at")
            .eq("receiver_id", int(uid))
            .order("created_at", desc=True)
            .limit(30)
            .execute()
        )
        if not rows:
            return result_str({
                "success": True,
                "action": "check_inbox",
                "unread": 0,
                "messages": [],
                "message": "信箱是空的，还没有人给你留言。",
            })

        sender_ids = [r["sender_id"] for r in rows if r.get("sender_id")]
        names = {}
        if sender_ids:
            name_rows = rows_of(
                client.table("fs_users").select("id, nickname").in_("id", sender_ids).execute()
            )
            names = {r["id"]: r["nickname"] for r in name_rows}

        messages = [{
            "from": names.get(r.get("sender_id"), "—"),
            "content": r.get("content") or "",
            "is_read": bool(r.get("is_read")),
            "sent_at": r.get("created_at"),
        } for r in rows]
        unread = sum(1 for m in messages if not m["is_read"])

        # 查看即已读
        if unread:
            client.table("fs_messages").update({"is_read": True}).eq("receiver_id", int(uid)).eq("is_read", False).execute()

        return result_str({
            "success": True,
            "action": "check_inbox",
            "unread": unread,
            "messages": messages,
            "message": f"共 {len(messages)} 条留言，其中 {unread} 条未读（已为你标记为已读）。",
        })
    except APIError as e:
        return err_str(f"信箱查询失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(f"信箱查询失败: {e}")

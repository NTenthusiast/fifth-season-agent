"""「第五季」个人板块工具：用户画像建档、待办管理、灵感记录（对话式入口的数据操作）"""

import random
from typing import Optional

from postgrest.exceptions import APIError

from storage.database.supabase_client import get_supabase_client
from tools.db_helpers import (
    as_row,
    err_str,
    find_user_by_nickname,
    result_str,
    rows_of,
)

from langchain.tools import tool

TODO_STATUSES = {"pending": "待办", "doing": "进行中", "done": "已完成"}


def _gen_legacy_code(client) -> str:
    """生成全库唯一的六位数字传承码（与 web 端注册同规则）"""
    for _ in range(50):
        code = f"{random.randint(0, 999999):06d}"
        hit = client.table("fs_users").select("id").eq("legacy_code", code).limit(1).execute()
        if not (hit.data or []):
            return code
    raise RuntimeError("传承码生成失败，请重试")


def _serialize_user(user: dict, include_contact: bool = False) -> dict:
    data = {
        "user_id": user["id"],
        "nickname": user["nickname"],
        "grade": user.get("grade"),
        "major": user.get("major"),
        "skill_tags": user.get("skill_tags") or [],
        "interest_tags": user.get("interest_tags") or [],
        "bio": user.get("bio"),
        "created_at": user.get("created_at"),
    }
    if include_contact:
        data["contact"] = user.get("contact")
    return data


@tool
def upsert_user_profile(
    nickname: str,
    grade: Optional[str] = None,
    major: Optional[str] = None,
    skill_tags: Optional[list[str]] = None,
    interest_tags: Optional[list[str]] = None,
    bio: Optional[str] = None,
    contact: Optional[str] = None,
) -> str:
    """按昵称为用户建档或更新档案。首次对话必须先建档。能力标签(skill_tags)与兴趣标签(interest_tags)是后续项目匹配与休眠唤醒推荐的数据基础，务必引导用户填写。

    Args:
        nickname: 用户昵称（档案唯一识别键，必填）
        grade: 年级/届别，如"2025级"
        major: 专业
        skill_tags: 能力标签列表，如["测绘设计","前端开发","文案写作"]
        interest_tags: 兴趣标签列表，如["公益","无障碍","校园改造"]
        bio: 个人简介
        contact: 联系方式（邮箱/微信等，仅当用户主动表示愿意被后来人联系时才填写，绝不主动索要）
    """
    nickname = (nickname or "").strip()
    if not nickname:
        return err_str("nickname 不能为空")
    try:
        existing = find_user_by_nickname(nickname)
        payload = {"nickname": nickname}
        if grade is not None:
            payload["grade"] = grade.strip() if grade.strip() else None
        if major is not None:
            payload["major"] = major.strip() if major.strip() else None
        if skill_tags is not None:
            payload["skill_tags"] = [t.strip() for t in skill_tags if t and t.strip()]
        if interest_tags is not None:
            payload["interest_tags"] = [t.strip() for t in interest_tags if t and t.strip()]
        if bio is not None:
            payload["bio"] = bio.strip() or None
        if contact is not None:
            payload["contact"] = contact.strip() or None

        client = get_supabase_client()
        if existing:
            resp = (
                client.table("fs_users").update(payload).eq("id", existing["id"]).execute()
            )
            if not rows_of(resp):
                return err_str("更新档案失败：未匹配到记录")
            return result_str(
                {
                    "success": True,
                    "action": "updated",
                    "message": f"已更新「{nickname}」的档案",
                    "user": _serialize_user(as_row(resp), include_contact=True),
                }
            )
        payload.setdefault("skill_tags", [])
        payload.setdefault("interest_tags", [])
        # v8.0：agent 侧建档也生成六位传承码（保证后续可登录、种子卡编号正确）
        payload["legacy_code"] = _gen_legacy_code(client)
        resp = client.table("fs_users").insert(payload).execute()
        created = as_row(resp)
        return result_str(
            {
                "success": True,
                "action": "created",
                "message": f"欢迎新同学！「{nickname}」档案已建立",
                "user": _serialize_user(created),
                "legacy_code_note": "已自动生成六位传承码，请转告用户妥善保存（用于下次登录）",
            }
        )
    except APIError as e:
        return err_str(f"建档失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def get_user_profile(nickname: str) -> str:
    """查询用户档案（按昵称）。用于会话开始时识别当前用户。若用户未建档会明确提示。

    Args:
        nickname: 用户昵称
    """
    try:
        user = find_user_by_nickname(nickname)
        if user is None:
            return result_str(
                {
                    "success": True,
                    "exists": False,
                    "message": f"「{nickname}」尚未建档，请引导用户注册（昵称/年级专业/能力标签/兴趣标签）",
                }
            )
        return result_str({"success": True, "exists": True, "user": _serialize_user(user)})
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def find_users_by_tags(tags: list[str], limit: int = 10) -> str:
    """按能力/兴趣标签检索候选用户（夏·生长"找伙伴"与第五季"人找项目"的匹配候选池）。
    返回每个候选人的标签命中情况，匹配度评估与组队理由由你在应答中完成。

    Args:
        tags: 匹配标签列表（能力或兴趣），如["测绘","公益"]
        limit: 最多返回人数，默认10
    """
    tags = [t.strip() for t in (tags or []) if t and t.strip()]
    if not tags:
        return err_str("tags 不能为空")
    limit = max(1, min(int(limit), 50))
    try:
        client = get_supabase_client()
        resp = (
            client.table("fs_users")
            .select("id, nickname, grade, major, skill_tags, interest_tags, bio")
            .limit(limit * 3)
            .execute()
        )
        scored = []
        for user in rows_of(resp):
            skills = set(user.get("skill_tags") or [])
            interests = set(user.get("interest_tags") or [])
            hit_skills = sorted(skills & set(tags))
            hit_interests = sorted(interests & set(tags))
            score = len(hit_skills) * 2 + len(hit_interests)
            if score > 0:
                scored.append(
                    {
                        "user_id": user["id"],
                        "nickname": user["nickname"],
                        "grade": user.get("grade"),
                        "major": user.get("major"),
                        "skill_tags": sorted(skills),
                        "interest_tags": sorted(interests),
                        "bio": user.get("bio"),
                        "hit_skill_tags": hit_skills,
                        "hit_interest_tags": hit_interests,
                        "tag_match_score": score,
                    }
                )
        scored.sort(key=lambda x: -x["tag_match_score"])
        return result_str(
            {
                "success": True,
                "query_tags": tags,
                "candidates": scored[:limit],
                "total": len(scored),
                "note": "请基于命中标签为用户评估互补度并给出组队/推荐理由，匹配结论可用 save_match_log 留存",
            }
        )
    except APIError as e:
        return err_str(f"检索用户失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def manage_todo(
    action: str,
    nickname: str,
    todo_id: Optional[int] = None,
    title: Optional[str] = None,
    due_at: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[int] = None,
) -> str:
    """管理当前用户的待办事项。action 支持：add(新增，需title)/list(查询，可按status过滤)/update(编辑，需todo_id)/set_status(改状态，需todo_id与status)/delete(删除，需todo_id)。
    待办可关联项目(project_id)，实现个人事务与校园项目联动。

    Args:
        action: 操作类型 add/list/update/set_status/delete
        nickname: 用户昵称
        todo_id: 待办id（update/set_status/delete 必填）
        title: 待办标题（add 必填）
        due_at: 截止时间 ISO8601 格式，如 "2026-09-01T18:00:00+08:00"
        status: 待办状态 pending/doing/done
        project_id: 关联项目id（可选）
    """
    action = (action or "").strip().lower()
    try:
        client = get_supabase_client()
        from tools.db_helpers import require_user_id

        uid = require_user_id(nickname)

        if action == "add":
            if not title or not title.strip():
                return err_str("新增待办必须提供 title")
            payload = {"user_id": uid, "title": title.strip()}
            if due_at:
                payload["due_at"] = due_at
            if status:
                if status not in TODO_STATUSES:
                    return err_str(f"status 仅支持 {list(TODO_STATUSES)}")
                payload["status"] = status
            if project_id is not None:
                payload["project_id"] = int(project_id)
            resp = client.table("fs_todos").insert(payload).execute()
            row = as_row(resp)
            return result_str(
                {
                    "success": True,
                    "action": "add",
                    "todo": row,
                    "status_name": TODO_STATUSES.get(row.get("status"), row.get("status")),
                    "message": f"待办已创建：{row['title']}",
                }
            )

        if action == "list":
            query = client.table("fs_todos").select(
                "id, title, due_at, status, project_id, created_at"
            )
            if status:
                if status not in TODO_STATUSES:
                    return err_str(f"status 仅支持 {list(TODO_STATUSES)}")
                query = query.eq("status", status)
            resp = query.eq("user_id", uid).order("created_at", desc=True).limit(100).execute()
            rows = rows_of(resp)
            return result_str(
                {
                    "success": True,
                    "action": "list",
                    "todos": rows,
                    "total": len(rows),
                    "status_names": TODO_STATUSES,
                }
            )

        if todo_id is None:
            return err_str("update/set_status/delete 操作必须提供 todo_id")

        if action == "update":
            payload = {}
            if title is not None and title.strip():
                payload["title"] = title.strip()
            if due_at is not None:
                payload["due_at"] = due_at or None
            if project_id is not None:
                payload["project_id"] = int(project_id)
            if not payload:
                return err_str("update 至少需要提供一个修改字段（title/due_at/project_id）")
            resp = (
                client.table("fs_todos")
                .update(payload)
                .eq("id", int(todo_id))
                .eq("user_id", uid)
                .execute()
            )
            if not rows_of(resp):
                return err_str(f"待办不存在或不属于「{nickname}」（todo_id={todo_id}）")
            return result_str({"success": True, "action": "update", "todo": as_row(resp)})

        if action == "set_status":
            if status not in TODO_STATUSES:
                return err_str(f"status 仅支持 {list(TODO_STATUSES)}")
            resp = (
                client.table("fs_todos")
                .update({"status": status})
                .eq("id", int(todo_id))
                .eq("user_id", uid)
                .execute()
            )
            if not rows_of(resp):
                return err_str(f"待办不存在或不属于「{nickname}」（todo_id={todo_id}）")
            row = as_row(resp)
            return result_str(
                {
                    "success": True,
                    "action": "set_status",
                    "todo": row,
                    "message": f"「{row['title']}」已标记为 {TODO_STATUSES[status]}",
                }
            )

        if action == "delete":
            resp = (
                client.table("fs_todos")
                .delete()
                .eq("id", int(todo_id))
                .eq("user_id", uid)
                .execute()
            )
            if not rows_of(resp):
                return err_str(f"待办不存在或不属于「{nickname}」（todo_id={todo_id}）")
            return result_str(
                {
                    "success": True,
                    "action": "delete",
                    "message": f"待办已删除：{as_row(resp)['title']}",
                }
            )

        return err_str(f"不支持的操作 action={action}，可用：add/list/update/set_status/delete")
    except APIError as e:
        return err_str(f"待办操作失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def manage_inspiration(
    action: str,
    nickname: str,
    content: Optional[str] = None,
    inspiration_id: Optional[int] = None,
    mark_converted: bool = False,
    project_id: Optional[int] = None,
    title: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """管理当前用户的个人种子卡（零碎灵感的建档，编号=传承码-序号，仅本人可见）。
    action 支持：add(新增，content 必填，title/tags 可选)/list(查询，返回种子卡编号)/convert(转化为项目)。
    当一个灵感经你提炼为公开种子卡（项目）后，用 mark_converted=true + project_id 标记已转化。

    Args:
        action: 操作类型 add/list/convert
        nickname: 用户昵称
        content: 灵感内容（add 必填，保留用户的原始表述）
        inspiration_id: 灵感id（convert 时必填）
        mark_converted: 是否将灵感标记为已转化为项目
        project_id: 转化后的项目id（mark_converted=true 时必填）
        title: 种子卡标题（add 可选，如"宿舍楼共享雨伞想法"）
        tags: 种子卡标签，逗号分隔（add 可选，如"生活服务,公益"）
    """
    action = (action or "").strip().lower()
    try:
        client = get_supabase_client()
        from tools.db_helpers import require_user_id

        uid = require_user_id(nickname)

        if action == "add":
            if not content or not content.strip():
                return err_str("新增灵感必须提供 content")
            insert = {"user_id": uid, "content": content.strip()}
            if title and str(title).strip():
                insert["title"] = str(title).strip()[:120]
            if tags:
                from tools.seed_tools import _norm_tags

                nt = _norm_tags(tags)
                if nt:
                    insert["tags"] = nt
            resp = (
                client.table("fs_inspirations")
                .insert(insert)
                .execute()
            )
            row = as_row(resp)
            from tools.seed_tools import _legacy_code_of

            lc = _legacy_code_of(client, uid)
            code = f"{lc}-{int(row['id']):03d}" if row else ""
            return result_str(
                {
                    "success": True,
                    "action": "add",
                    "inspiration": row,
                    "seed_code": code,
                    "message": f"灵感已存入你的个人种子库（种子卡编号 {code}，仅你可见）",
                }
            )

        if action == "list":
            resp = (
                client.table("fs_inspirations")
                .select("id, title, tags, content, status, project_id, created_at")
                .eq("user_id", uid)
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            from tools.seed_tools import _legacy_code_of

            lc = _legacy_code_of(client, uid)
            items = []
            for r in rows_of(resp):
                r = dict(r)
                r["seed_code"] = f"{lc}-{int(r['id']):03d}"
                items.append(r)
            return result_str(
                {
                    "success": True,
                    "action": "list",
                    "inspirations": items,
                    "total": len(items),
                    "message": "以上为用户的个人种子卡（编号=传承码-序号，仅本人可见）",
                }
            )

        if action == "convert" or mark_converted:
            if inspiration_id is None or project_id is None:
                return err_str("转化灵感必须提供 inspiration_id 与 project_id")
            resp = (
                client.table("fs_inspirations")
                .update({"status": "converted", "project_id": int(project_id)})
                .eq("id", int(inspiration_id))
                .eq("user_id", uid)
                .execute()
            )
            if not rows_of(resp):
                return err_str(f"灵感不存在或不属于「{nickname}」（inspiration_id={inspiration_id}）")
            return result_str(
                {
                    "success": True,
                    "action": "convert",
                    "inspiration": as_row(resp),
                    "message": f"灵感已转化为项目 #{project_id} 的种子",
                }
            )

        return err_str(f"不支持的操作 action={action}，可用：add/list/convert")
    except APIError as e:
        return err_str(f"灵感操作失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def find_mentors(nickname: str, domain: str = "") -> str:
    """为后来人寻找可联系的前辈：在已建档用户中，按能力/兴趣标签的匹配度推荐与用户同方向的人。留了联系方式的前辈会展示联系方式（本人建档时自愿公开），未留的标注"未留联系方式"。适合：用户想找同方向学长学姐请教、或接棒前想联系原团队。

    Args:
        nickname: 当前用户昵称（用于计算匹配度并排除自己，必填）
        domain: 可选，限定方向关键词，如"环保"/"支教"/"前端"，会与对方标签做包含匹配
    """
    nickname = (nickname or "").strip()
    if not nickname:
        return err_str("nickname 不能为空")
    try:
        me = find_user_by_nickname(nickname)
        if not me:
            return err_str(f"「{nickname}」尚未建档，请先调用 upsert_user_profile 建档")
        client = get_supabase_client()
        others = rows_of(
            client.table("fs_users")
            .select("id,nickname,grade,major,skill_tags,interest_tags,bio,contact")
            .neq("id", me["id"])
            .execute()
        )
        my_skills = set(me.get("skill_tags") or [])
        my_interests = set(me.get("interest_tags") or [])
        scored = []
        for u in others:
            if u.get("major") and "档案" in (u.get("major") or ""):
                continue  # 档案级组织账号不作为个人前辈推荐
            sk = set(u.get("skill_tags") or [])
            it = set(u.get("interest_tags") or [])
            overlap = (my_skills & sk) | (my_interests & it)
            if domain:
                kw = domain.strip()
                if not (kw in sk or kw in it or kw in (u.get("major") or "") or kw in " ".join(it | sk)):
                    continue
            if not overlap and not domain:
                continue
            scored.append(
                {
                    "nickname": u["nickname"],
                    "grade": u.get("grade"),
                    "major": u.get("major"),
                    "match_tags": sorted(overlap)[:6],
                    "contact": (u.get("contact") or "").strip() or "未留联系方式",
                    "contact_public": bool((u.get("contact") or "").strip()),
                    "bio": (u.get("bio") or "")[:60],
                }
            )
        scored.sort(key=lambda x: -len(x["match_tags"]))
        return result_str(
            {
                "success": True,
                "count": len(scored),
                "mentors": scored[:8],
                "note": "联系方式仅展示建档时自愿公开的用户；未留联系方式的前辈可通过站内昵称先建立连接",
            }
        )
    except APIError as e:
        return err_str(f"查找前辈失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))

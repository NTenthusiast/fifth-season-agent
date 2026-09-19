"""「第五季」v10.0 个人项目库工具：完整项目信息（仅本人可见）+ 知颜生成交接包 + 公开授权"""

import json
from datetime import date
from typing import Optional

from postgrest.exceptions import APIError

from storage.database.supabase_client import get_supabase_client
from tools.db_helpers import (
    as_row,
    err_str,
    require_user_id,
    result_str,
    rows_of,
    safe_maybe_single,
)

from langchain.tools import tool

PROJECT_STATUSES = {
    "ongoing": "进行中",
    "unfinished": "未完成",
    "taken_over": "接棒中",
    "done": "已完成",
}


def _pkg_from_row(row: dict) -> Optional[dict]:
    pkg = row.get("handover_package")
    if isinstance(pkg, str) and pkg.strip():
        try:
            pkg = json.loads(pkg)
        except (ValueError, TypeError):
            pkg = None
    return pkg if isinstance(pkg, dict) else None


@tool
def manage_personal_project(
    action: str,
    nickname: str,
    project_id: Optional[int] = None,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    tags: Optional[str] = None,
    source_project_id: Optional[int] = None,
    handover_public: Optional[bool] = None,
    achievements: Optional[list[str]] = None,
    experience: Optional[list[str]] = None,
    pitfalls: Optional[list[str]] = None,
    remaining_issues: Optional[list[str]] = None,
    reusable_resources: Optional[list[str]] = None,
    authorization_scope: Optional[str] = None,
    resource_valid_until: Optional[str] = None,
    founder_rights: Optional[str] = None,
) -> str:
    """管理当前用户的个人项目库（区别于种子卡：包含项目完整信息、仅本人可见，可存放未完成或接棒的项目）。
    项目编号为 PJ-#N。action 支持：
    - create: 新建项目（title 必填；summary/description/status/tags/source_project_id 可选）
    - list: 列出我库中的全部项目（含编号、状态、是否有交接包、是否公开）
    - detail: 查看某项目完整信息（project_id 必填）
    - update: 更新项目信息（project_id 必填，字段可选）
    - delete: 删除项目（project_id 必填）
    - generate_handover: 由你（知颜）基于项目完整信息提炼五段式交接包并归档到该项目（project_id 必填，
      achievements/experience/pitfalls/remaining_issues/reusable_resources 五段每段至少 1 条，
      另须给出 authorization_scope/resource_valid_until/founder_rights 三项治理声明；禁止编造）
    - set_public: 设置交接包是否公开（project_id + handover_public 必填；公开后他人可在公开种子库
      或通过与你的对话获取该交接包）

    Args:
        action: 操作类型 create/list/detail/update/delete/generate_handover/set_public
        nickname: 用户昵称
        project_id: 个人项目库中的项目 id
        title: 项目名称
        summary: 一句话简介（≤200字）
        description: 项目完整描述：目标、进展、成果、当前状态等（≤4000字）
        status: 项目状态 ongoing(进行中)/unfinished(未完成)/taken_over(接棒中)/done(已完成)
        tags: 项目标签，逗号分隔
        source_project_id: 来源公开种子卡项目id（接棒时记录）
        handover_public: 交接包是否公开
        achievements: 项目成果列表（generate_handover 必填）
        experience: 执行经验列表（generate_handover 必填）
        pitfalls: 踩坑总结列表（generate_handover 必填）
        remaining_issues: 遗留问题/未完成任务列表（generate_handover 必填）
        reusable_resources: 可复用资源列表（generate_handover 必填）
        authorization_scope: 成果授权范围（generate_handover 必填）
        resource_valid_until: 资源有效期，YYYY-MM-DD 或"长期有效"（generate_handover 必填）
        founder_rights: 原团队权益保护（generate_handover 必填）
    """
    action = (action or "").strip().lower()
    try:
        client = get_supabase_client()
        uid = require_user_id(nickname)
        table = client.table("fs_personal_projects")

        if action == "create":
            if not (title or "").strip():
                return err_str("新建项目必须提供 title")
            st = (status or "ongoing").strip().lower()
            if st not in PROJECT_STATUSES:
                return err_str(f"status 仅支持：{'/'.join(PROJECT_STATUSES)}")
            insert = {
                "user_id": uid,
                "title": title.strip()[:80],
                "summary": (summary or "").strip()[:200],
                "description": (description or "").strip()[:4000],
                "status": st,
            }
            if source_project_id:
                insert["source_project_id"] = int(source_project_id)
            if tags and str(tags).strip():
                from tools.seed_tools import _norm_tags

                nt = _norm_tags(tags)
                if nt:
                    insert["tags"] = nt
            row = as_row(table.insert(insert).execute())
            pid = int(row["id"])
            return result_str(
                {
                    "success": True,
                    "action": "create",
                    "project": {"id": pid, "fs_code": f"PJ-{pid:03d}", "title": row["title"], "status": st},
                    "message": f"项目「{row['title']}」已存入你的个人项目库（编号 PJ-{pid:03d}，仅你可见）",
                }
            )

        if action == "list":
            rows = rows_of(
                table.select("id, title, summary, status, tags, handover_package, handover_public, source_project_id, updated_at")
                .eq("user_id", uid)
                .order("updated_at", desc=True)
                .limit(100)
                .execute()
            )
            items = []
            for r in rows:
                items.append(
                    {
                        "id": r["id"],
                        "fs_code": f"PJ-{int(r['id']):03d}",
                        "title": r["title"],
                        "summary": r.get("summary") or "",
                        "status": PROJECT_STATUSES.get(r.get("status") or "ongoing", r.get("status")),
                        "tags": r.get("tags") or [],
                        "has_handover": bool(_pkg_from_row(r)),
                        "handover_public": bool(r.get("handover_public")),
                        "source_project_id": r.get("source_project_id"),
                        "updated_at": r.get("updated_at"),
                    }
                )
            return result_str(
                {
                    "success": True,
                    "action": "list",
                    "total": len(items),
                    "projects": items,
                    "message": f"你的个人项目库共有 {len(items)} 个项目（编号 PJ-#N，仅你可见）",
                }
            )

        if project_id is None:
            return err_str(f"action={action} 需要提供 project_id")
        pid = int(project_id)
        row = safe_maybe_single(
            table.select("*").eq("id", pid).eq("user_id", uid)
        )
        if not row:
            return err_str(f"个人项目库中不存在 id={pid} 的项目（仅能操作本人项目）")

        if action == "detail":
            row = dict(row)
            pkg = _pkg_from_row(row)
            row["fs_code"] = f"PJ-{pid:03d}"
            row["status_label"] = PROJECT_STATUSES.get(row.get("status") or "ongoing", row.get("status"))
            row["handover_package"] = pkg
            row["has_handover"] = bool(pkg)
            return result_str(
                {
                    "success": True,
                    "action": "detail",
                    "project": row,
                    "message": f"PJ-{pid:03d}「{row['title']}」完整信息如下",
                }
            )

        if action == "update":
            patch = {}
            if title and title.strip():
                patch["title"] = title.strip()[:80]
            if summary is not None:
                patch["summary"] = summary.strip()[:200]
            if description is not None:
                patch["description"] = description.strip()[:4000]
            if status and status.strip().lower() in PROJECT_STATUSES:
                patch["status"] = status.strip().lower()
            if tags and str(tags).strip():
                from tools.seed_tools import _norm_tags

                nt = _norm_tags(tags)
                if nt:
                    patch["tags"] = nt
            if not patch:
                return err_str("update 需要至少一个要更新的字段（title/summary/description/status/tags）")
            resp = table.update(patch).eq("id", pid).eq("user_id", uid).execute()
            return result_str(
                {
                    "success": True,
                    "action": "update",
                    "updated_fields": list(patch.keys()),
                    "message": f"PJ-{pid:03d} 已更新：{ '、'.join(patch.keys()) }",
                }
            )

        if action == "delete":
            table.delete().eq("id", pid).eq("user_id", uid).execute()
            return result_str(
                {"success": True, "action": "delete", "message": f"PJ-{pid:03d} 已从你的个人项目库删除"}
            )

        if action == "set_public":
            if handover_public is None:
                return err_str("set_public 需要提供 handover_public (true/false)")
            if handover_public and not _pkg_from_row(row):
                return err_str("该项目还没有交接包：请先与我对话提炼生成（generate_handover），再选择公开")
            resp = (
                table.update({"handover_public": bool(handover_public)})
                .eq("id", pid)
                .eq("user_id", uid)
                .execute()
            )
            state = "已公开" if handover_public else "已转为仅自己可见"
            return result_str(
                {
                    "success": True,
                    "action": "set_public",
                    "handover_public": bool(handover_public),
                    "message": f"PJ-{pid:03d} 的交接包{state}"
                    + ("；他人现在可以在公开种子库获取，或在与我的对话中凭编号获取" if handover_public else ""),
                }
            )

        if action == "generate_handover":
            fields = {
                "achievements": achievements,
                "experience": experience,
                "pitfalls": pitfalls,
                "remaining_issues": remaining_issues,
                "reusable_resources": reusable_resources,
            }
            governance = {
                "authorization_scope": (authorization_scope or "").strip(),
                "resource_valid_until": (resource_valid_until or "").strip(),
                "founder_rights": (founder_rights or "").strip(),
            }
            if not all(governance.values()):
                return err_str("交接包必须补齐授权范围、资源有效期、原团队权益保护三项治理声明")
            if governance["resource_valid_until"] != "长期有效":
                try:
                    expiry = date.fromisoformat(governance["resource_valid_until"])
                except ValueError:
                    return err_str("资源有效期请使用 YYYY-MM-DD 或填写“长期有效”")
                if expiry < date.today():
                    return err_str("资源有效期不能早于今天；过期资料须重新核验后再交接")
            clean = {}
            for k, v in fields.items():
                items = [str(i).strip() for i in (v or []) if str(i).strip()]
                if not items:
                    return err_str(f"交接包「{k}」段不能为空，请基于项目完整信息提炼至少 1 条，禁止编造")
                clean[k] = items
            clean["reusable_resources"].extend(
                [
                    f"【授权范围】{governance['authorization_scope']}",
                    f"【资源有效期】{governance['resource_valid_until']}",
                    f"【原团队权益】{governance['founder_rights']}",
                ]
            )
            pkg_json = {
                **clean,
                "authorization_scope": governance["authorization_scope"],
                "resource_valid_until": governance["resource_valid_until"],
                "founder_rights": governance["founder_rights"],
                "generated_by": "知颜",
            }
            table.update({"handover_package": json.dumps(pkg_json, ensure_ascii=False)}).eq("id", pid).eq("user_id", uid).execute()
            return result_str(
                {
                    "success": True,
                    "action": "generate_handover",
                    "fs_code": f"PJ-{pid:03d}",
                    "sections": {k: len(v) for k, v in clean.items()},
                    "governance": governance,
                    "message": f"PJ-{pid:03d}「{row['title']}」的交接包已生成并归档到你的个人项目库；"
                    "若想让他人获取，可以让我把它设为公开（set_public），或自己在「项目库」面板中打开公开开关",
                }
            )

        return err_str(f"不支持的操作 action={action}，可用：create/list/detail/update/delete/generate_handover/set_public")
    except APIError as e:
        return err_str(f"个人项目库操作失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def get_public_handover(fs_code: str, nickname: Optional[str] = None) -> str:
    """按编号获取公开种子卡的交接包（他人公开授权的交接包可凭编号获取）。
    编号规则：FS-#N 为公开种子库项目（如 FS-017），PJ-#N 为他人个人项目库公开的项目（如 PJ-003）。
    仅返回已获授权公开（handover_public=true）的交接包；未公开的会提示需要项目主人授权。

    Args:
        fs_code: 种子卡编号，如 FS-017 或 PJ-003
        nickname: 当前用户昵称（可选）
    """
    code = (fs_code or "").strip().upper()
    try:
        client = get_supabase_client()

        def _finish(row: dict, kind: str, code_str: str, owner_name: str) -> str:
            return result_str(
                {
                    "success": True,
                    "fs_code": code_str,
                    "kind": kind,
                    "project": {"id": row.get("id"), "title": row.get("title"), "owner_nickname": owner_name},
                    "handover": row.get("handover"),
                    "message": f"已获取 {code_str}「{row.get('title')}」的交接包（由 {owner_name} 公开授权）",
                }
            )

        if code.startswith("PJ-"):
            try:
                pid = int(code.replace("PJ-", "").strip())
            except ValueError:
                return err_str(f"编号格式不正确：{fs_code}，应为 PJ-#N（如 PJ-003）")
            row = safe_maybe_single(
                client.table("fs_personal_projects")
                .select("id, title, user_id, handover_package, handover_public")
                .eq("id", pid)
            )
            if not row:
                return err_str(f"不存在编号 {code} 的项目")
            owner = safe_maybe_single(client.table("fs_users").select("nickname").eq("id", int(row["user_id"])))
            owner_name = (owner or {}).get("nickname") or "—"
            if not row.get("handover_public"):
                return err_str(f"{code}「{row['title']}」的交接包尚未获得项目主人（{owner_name}）公开授权，暂不可获取；可请 TA 在个人项目库中打开公开开关")
            pkg = row.get("handover_package")
            if isinstance(pkg, str) and pkg.strip():
                try:
                    pkg = json.loads(pkg)
                except (ValueError, TypeError):
                    pkg = None
            if not isinstance(pkg, dict) or not pkg:
                return err_str(f"{code}「{row['title']}」还没有生成交接包")
            row["handover"] = pkg
            return _finish(row, "personal", code, owner_name)

        if code.startswith("FS-"):
            try:
                pid = int(code.replace("FS-", "").strip())
            except ValueError:
                return err_str(f"编号格式不正确：{fs_code}，应为 FS-#N（如 FS-017）")
            proj = safe_maybe_single(
                client.table("fs_projects")
                .select("id, title, founder_id, owner_id, handover_public")
                .eq("id", pid)
            )
            if not proj:
                return err_str(f"不存在编号 {code} 的项目")
            owner_name = "—"
            for uid_field in ("owner_id", "founder_id"):
                if proj.get(uid_field):
                    u = safe_maybe_single(client.table("fs_users").select("nickname").eq("id", int(proj[uid_field])))
                    if u:
                        owner_name = u.get("nickname") or "—"
                        break
            if not proj.get("handover_public"):
                is_owner = False
                if nickname:
                    try:
                        uid = require_user_id(nickname)
                        is_owner = uid in (int(proj.get("founder_id") or 0), int(proj.get("owner_id") or 0))
                    except Exception:  # noqa: BLE001
                        is_owner = False
                if not is_owner:
                    return err_str(f"{code}「{proj['title']}」的交接包尚未获得项目主人（{owner_name}）公开授权，暂不可获取")
            pkg_rows = rows_of(
                client.table("fs_handover_packages")
                .select("achievements,experience,pitfalls,remaining_issues,reusable_resources,created_at")
                .eq("project_id", pid)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if not pkg_rows:
                return err_str(f"{code}「{proj['title']}」还没有生成交接包")
            pkg = dict(pkg_rows[0])
            for k in ("achievements", "experience", "pitfalls", "remaining_issues", "reusable_resources"):
                v = pkg.get(k)
                if isinstance(v, str) and v.strip():
                    try:
                        parsed = json.loads(v)
                        pkg[k] = parsed if isinstance(parsed, list) else [v]
                    except (ValueError, TypeError):
                        pkg[k] = [seg.strip() for seg in v.split(",") if seg.strip()]
                elif not isinstance(v, list):
                    pkg[k] = []
            proj["handover"] = pkg
            return _finish(proj, "fs", code, owner_name)

        return err_str(f"无法识别的编号：{fs_code}（支持 FS-#N 公开种子卡 / PJ-#N 个人项目库项目）")
    except APIError as e:
        return err_str(f"获取交接包失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))

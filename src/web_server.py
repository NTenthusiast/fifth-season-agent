"""「第五季·续种」网页服务模块。

提供两种使用方式:
1. 注册到平台标准服务: 在 main.py 中调用 register_web(app) —— 推荐, 平台预览入口直达;
2. 独立运行调试: python src/web_server.py (默认 8000 端口, 禁用 9000 平台保留端口)。

路由:
- GET  /            首页 (assets/web/index.html)
- GET  /static/*    静态资源 (style.css / app.js)
- GET  /api/health  健康检查 (含 agent_ready)
- POST /api/chat    SSE 流式对话 (session_id 区分会话, 服务端短期记忆)
"""

import asyncio
import argparse
import json
import logging
from datetime import datetime
import os
import threading
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain.messages import AIMessageChunk, HumanMessage

from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context

from tools.db_helpers import rows_of, safe_maybe_single

logger = logging.getLogger("fifth_season.web")

# 静态资源目录: src/ 的上一级 assets/web
WEB_DIR = Path(__file__).resolve().parent.parent / "assets" / "web"

# 懒加载的 Agent 图 (线程安全)
_agent_graph = None
_agent_lock = threading.Lock()


def _load_agent():
    """加载 Agent 图 (首次调用时懒加载, 兼容任意宿主 app 的生命周期)。"""
    global _agent_graph
    if _agent_graph is None:
        with _agent_lock:
            if _agent_graph is None:
                from coze_coding_utils.helper.graph_helper import get_agent_instance

                logger.info("[web] loading agent instance ...")
                _agent_graph = get_agent_instance("agents.agent", None)
                logger.info("[web] agent instance ready")
    return _agent_graph


_agent_graph_no_mem = None
_agent_lock_no_mem = threading.Lock()


def _load_agent_no_memory():
    """加载无 checkpointer 的 Agent 图（数据库故障时对话降级，保证可聊）。"""
    global _agent_graph_no_mem
    if _agent_graph_no_mem is None:
        with _agent_lock_no_mem:
            if _agent_graph_no_mem is None:
                from agents.agent import build_agent

                logger.info("[web] loading no-memory agent instance ...")
                _agent_graph_no_mem = build_agent(None, use_memory=False)
                logger.info("[web] no-memory agent instance ready")
    return _agent_graph_no_mem


def _is_conn_error(e: BaseException) -> bool:
    """判定是否为数据库/连接类故障（可降级重跑）。"""
    text = f"{type(e).__name__}: {e}"
    keys = (
        "PoolTimeout", "couldn't get a connection", "psycopg",
        "Network is unreachable", "connection is bad", "connection timeout",
        "OperationalError", "PGRST002", "Missing response",
    )
    return any(k in text for k in keys)


def _sse(payload: Dict[str, Any]) -> str:
    """SSE 数据帧。"""
    import json

    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# 工具名 → 面向用户的进度提示。模型一个回合里可能连续调用多个工具，
# 若只等最终文本，用户会长时间盯着空白气泡——这是"体感很笨"的主要来源。
_TOOL_LABELS: Dict[str, str] = {
    "upsert_user_profile": "正在建立你的档案…",
    "get_user_profile": "正在查阅你的档案…",
    "find_users_by_tags": "正在寻找匹配的同学…",
    "send_message": "正在投递留言到对方信箱…",
    "check_my_inbox": "正在查看你的信箱…",
    "manage_todo": "正在整理待办…",
    "manage_inspiration": "正在记录灵感…",
    "create_project": "正在生成项目种子卡…",
    "search_projects": "正在检索校园项目库…",
    "get_project_detail": "正在调取项目完整资料…",
    "update_project": "正在更新种子卡…",
    "advance_project_stage": "正在推进项目阶段…",
    "add_project_update": "正在记录项目进展…",
    "add_project_member": "正在添加项目成员…",
    "save_handover_package": "正在提炼交接包…",
    "awaken_project": "正在唤醒休眠种子…",
    "save_match_log": "正在留存匹配结论…",
    "get_reminders": "正在整理提醒事项…",
    "school_issue_insight": "正在汇总校园议题…",
    "get_relay_stories": "正在翻阅传承故事墙…",
    "generate_handover_certificate": "正在生成托付书…",
    "generate_seed_poster": "正在生成分享海报…",
    "get_project_health": "正在进行项目巡检…",
    "get_skill_graph": "正在统计技能供需…",
    "vote_awaken_request": "正在记录你的投票…",
    "get_my_awards": "正在核对你的成就…",
    "discover_project_synergy": "正在寻找协作机会…",
    "import_from_github": "正在读取 GitHub 仓库…",
    "read_upload": "正在通读你上传的文件…",
    "upsert_profile": "正在描绘你的画像…",
    "match_seed_partners": "正在寻找能力互补的搭档…",
    "team_overview": "正在查看你的团队…",
}


def register_web(app: FastAPI) -> None:
    """将网页能力注册到宿主 FastAPI 应用 (main.py 平台服务)。"""

    # --- 首页 ---
    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(
            WEB_DIR / "index.html",
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    # --- 静态资源 (no-cache: 保证修复/迭代即时生效, ETag 仍可协商缓存) ---
    if WEB_DIR.is_dir():
        app.mount(
            "/static",
            StaticFiles(directory=str(WEB_DIR)),
            name="web-static",
        )

        # 参赛交付物（项目文档 PDF/HTML）：挂载 docs/ 供评委直接下载
        docs_dir = WEB_DIR.parent.parent / "docs"
        if docs_dir.is_dir():
            app.mount("/docs", StaticFiles(directory=str(docs_dir)), name="docs-static")

        @app.middleware("http")
        async def _static_no_cache(request, call_next):
            resp = await call_next(request)
            if request.url.path.startswith("/static"):
                resp.headers["Cache-Control"] = "no-cache, must-revalidate"
            return resp

    # --- 健康检查 ---
    @app.get("/api/health")
    async def api_health() -> JSONResponse:
        return JSONResponse({"status": "ok", "agent_ready": _agent_graph is not None})

    # ==================== v7.0 认证体系（昵称 + 六位传承码） ====================
    import random as _random

    def _gen_legacy_code(client) -> str:
        """生成全库唯一的六位数字传承码"""
        for _ in range(50):
            code = f"{_random.randint(0, 999999):06d}"
            hit = client.table("fs_users").select("id").eq("legacy_code", code).limit(1).execute()
            if not (hit.data or []):
                return code
        raise RuntimeError("传承码生成失败，请重试")

    def _unread_count(client, user_id: int) -> int:
        rows = client.table("fs_messages").select("id").eq("receiver_id", int(user_id)).eq("is_read", False).execute()
        return len(rows.data or [])

    def _hdr_utf8(value: str) -> str:
        """HTTP header 以 latin-1 传输中文，转回 UTF-8（浏览器 fetch 按 UTF-8 发送）。"""
        try:
            return value.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value

    def _auth_user(request: Request) -> Dict[str, Any]:
        """读取登录态：优先 X-FS-Nickname/X-FS-Code 请求头（ASCII 昵称），
        其次 fs_auth cookie（中文昵称经 URL 编码传输，浏览器 fetch 限制 header 值）。失败抛 PermissionError（401）"""
        nickname = _hdr_utf8(request.headers.get("X-FS-Nickname") or "").strip()
        code = (request.headers.get("X-FS-Code") or "").strip()
        if not nickname or not code:
            cookie_raw = request.cookies.get("fs_auth") or ""
            if cookie_raw:
                try:
                    from urllib.parse import unquote
                    cred = json.loads(unquote(cookie_raw))
                    nickname = str(cred.get("n") or "").strip()
                    code = str(cred.get("c") or "").strip()
                except Exception:  # noqa: BLE001
                    raise PermissionError("登录态已失效，请重新登录")
            else:
                raise PermissionError("请先登录")
        from storage.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        user = safe_maybe_single(
            client.table("fs_users")
            .select("id, nickname, grade, major, school, skill_tags, interest_tags, bio, legacy_code, intro_done, persona, profile_public")
            .eq("nickname", nickname)
        )
        if not user or (user.get("legacy_code") or "") != code:
            raise PermissionError("昵称或传承码不正确")
        user.pop("legacy_code", None)
        return user

    def _register_action(nickname: str, grade: str, major: str) -> Dict[str, Any]:
        import re as _re
        from storage.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        nickname = (nickname or "").strip()
        grade = (grade or "").strip()
        major = (major or "").strip()
        if not nickname or len(nickname) > 24:
            raise ValueError("昵称必填，长度 1-24 个字符")
        if not _re.match(r"^20\d{2}级$", grade):
            raise ValueError("年级格式应为「202X级」")
        if not major or len(major) > 40:
            raise ValueError("专业必填")
        existed = safe_maybe_single(client.table("fs_users").select("id").eq("nickname", nickname))
        if existed:
            raise ValueError(f"昵称「{nickname}」已被注册，换一个试试")
        code = _gen_legacy_code(client)
        resp = client.table("fs_users").insert({
            "nickname": nickname, "grade": grade, "major": major,
            "skill_tags": [], "interest_tags": [],
            "legacy_code": code, "school": "南京大学",
        }).execute()
        row = (resp.data or [{}])[0]
        return {
            "user": {"id": row.get("id"), "nickname": nickname, "grade": grade, "major": major},
            "legacy_code": code,
            "message": "注册成功。传承码仅此一次完整展示，请务必抄写保存。",
        }

    @app.post("/api/auth/register")
    async def api_auth_register(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            payload = await asyncio.to_thread(
                _register_action,
                str((body or {}).get("nickname") or ""),
                str((body or {}).get("grade") or ""),
                str((body or {}).get("major") or ""),
            )
            return JSONResponse(payload)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] register failed: %s", e)
            return JSONResponse(status_code=500, content={"error": "注册失败，请稍后重试"})

    def _login_action(nickname: str, code: str) -> Dict[str, Any]:
        from storage.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        nickname = (nickname or "").strip()
        code = (code or "").strip()
        user = safe_maybe_single(
            client.table("fs_users")
            .select("id, nickname, grade, major, school, skill_tags, interest_tags, bio, legacy_code")
            .eq("nickname", nickname)
        )
        if not user:
            raise ValueError("该昵称尚未注册")
        if not user.get("legacy_code"):
            raise ValueError("该账号未设置传承码，请联系管理员重置")
        if user["legacy_code"] != code:
            raise ValueError("传承码不正确")
        user.pop("legacy_code", None)
        return {"user": user, "unread": _unread_count(client, user["id"])}

    @app.post("/api/auth/login")
    async def api_auth_login(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            payload = await asyncio.to_thread(
                _login_action,
                str((body or {}).get("nickname") or ""),
                str((body or {}).get("legacy_code") or ""),
            )
            return JSONResponse(payload)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] login failed: %s", e)
            return JSONResponse(status_code=500, content={"error": "登录失败，请稍后重试"})

    @app.get("/api/auth/me")
    async def api_auth_me(request: Request) -> JSONResponse:
        try:
            def _query(user_id: int) -> Dict[str, Any]:
                from storage.database.supabase_client import get_supabase_client

                client = get_supabase_client()
                return {"user": _me_user, "unread": _unread_count(client, user_id)}

            _me_user = await asyncio.to_thread(_auth_user, request)
            payload = await asyncio.to_thread(_query, _me_user["id"])
            return JSONResponse(payload)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] auth me failed: %s", e)
            return JSONResponse(status_code=500, content={"error": "查询失败"})

    # ==================== v7.0 留言信箱 ====================
    def _inbox_action(user_id: int) -> Dict[str, Any]:
        from tools.db_helpers import fetch_user_names
        from storage.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        rows = client.table("fs_messages").select(
            "id, sender_id, content, is_read, created_at"
        ).eq("receiver_id", int(user_id)).order("created_at", desc=True).limit(50).execute().data or []
        sender_ids = [r["sender_id"] for r in rows if r.get("sender_id")]
        names = fetch_user_names(sender_ids) if sender_ids else {}
        messages = [{
            "id": r["id"],
            "sender_nickname": names.get(r.get("sender_id"), "—"),
            "content": r.get("content") or "",
            "is_read": bool(r.get("is_read")),
            "created_at": r.get("created_at"),
        } for r in rows]
        # 拉取即视为已读
        client.table("fs_messages").update({"is_read": True}).eq("receiver_id", int(user_id)).eq("is_read", False).execute()
        return {"messages": messages}

    @app.get("/api/messages/inbox")
    async def api_messages_inbox(request: Request) -> JSONResponse:
        try:
            user = await asyncio.to_thread(_auth_user, request)
            payload = await asyncio.to_thread(_inbox_action, user["id"])
            return JSONResponse(payload)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] inbox query failed: %s", e)
            return JSONResponse(status_code=500, content={"error": "信箱查询失败"})

    # --- 首页实时统计 (真实数据库查询) ---
    @app.get("/api/stats")
    async def api_stats() -> JSONResponse:
        def _query() -> Dict[str, int]:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            users = client.table("fs_users").select("id").execute()
            projects = client.table("fs_projects").select("id").execute()
            awakened = client.table("fs_awaken_records").select("id").execute()
            return {
                "users": len(users.data or []),
                "projects": len(projects.data or []),
                "awakened": len(awakened.data or []),
            }

        try:
            stats = await asyncio.to_thread(_query)
            return JSONResponse(stats)
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] stats query failed: %s", e)
            return JSONResponse({"users": 0, "projects": 0, "awakened": 0})

    # --- 决赛验证中心：只展示数据库可追溯事实，不把演示数据包装成试点结论 ---
    @app.get("/api/evidence")
    async def api_evidence() -> JSONResponse:
        def _query_evidence() -> Dict[str, Any]:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            projects = client.table("fs_projects").select("id, stage").execute().data or []
            handovers = client.table("fs_handover_packages").select("project_id").execute().data or []
            awakens = client.table("fs_awaken_records").select("id, project_id").execute().data or []
            stories = client.table("fs_stories").select("id").execute().data or []
            dormant_ids = {int(p["id"]) for p in projects if p.get("stage") == "winter"}
            handover_ids = {int(h["project_id"]) for h in handovers if h.get("project_id") is not None}
            covered = len(dormant_ids & handover_ids)

            # --- 真实续种试点实录：全部数据取自库表，可逐条复核 ---
            pilot_case_ids = [17, 15]
            proj_rows = (
                client.table("fs_projects")
                .select("id, title, stage, owner_id")
                .in_("id", pilot_case_ids)
                .execute()
                .data
                or []
            )
            proj_map = {int(p["id"]): p for p in proj_rows}
            awaken_rows = (
                client.table("fs_awaken_records")
                .select("project_id, successor_id, awakened_at")
                .in_("project_id", pilot_case_ids)
                .order("id", desc=True)
                .execute()
                .data
                or []
            )
            awaken_map = {}
            for a in awaken_rows:
                awaken_map.setdefault(int(a["project_id"]), a)
            successor_ids = [a.get("successor_id") for a in awaken_map.values()]
            user_rows = (
                client.table("fs_users")
                .select("id, nickname, grade, major")
                .in_("id", [i for i in successor_ids if i is not None])
                .execute()
                .data
                or []
            )
            user_map = {int(u["id"]): u for u in user_rows}
            match_rows = (
                client.table("fs_match_logs")
                .select("user_id, project_id, match_score, match_reason, created_at")
                .eq("match_type", "user_to_project")
                .in_("project_id", pilot_case_ids)
                .order("id", desc=True)
                .execute()
                .data
                or []
            )
            match_map = {}
            for m in match_rows:
                match_map.setdefault((int(m["user_id"]), int(m["project_id"])), m)

            cases = []
            for pid in pilot_case_ids:
                proj = proj_map.get(pid)
                awaken = awaken_map.get(pid)
                if not proj or not awaken:
                    continue
                succ_id = awaken.get("successor_id")
                succ = user_map.get(int(succ_id)) if succ_id is not None else None
                match = match_map.get((int(succ_id), pid)) if succ_id is not None else None
                vote_rows = (
                    client.table("fs_votes")
                    .select("voter_nickname")
                    .eq("project_id", pid)
                    .execute()
                    .data
                    or []
                )
                handover_row = (
                    client.table("fs_handover_packages")
                    .select("achievements, experience, pitfalls, remaining_issues, reusable_resources")
                    .eq("project_id", pid)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                readiness = None
                if handover_row:
                    from tools.project_tools import assess_transfer_readiness

                    updates_count = len(
                        client.table("fs_project_updates")
                        .select("id")
                        .eq("project_id", pid)
                        .execute()
                        .data
                        or []
                    )
                    readiness = assess_transfer_readiness(handover_row[0], [{"id": i} for i in range(updates_count)])
                cases.append({
                    "project_id": pid,
                    "project_title": proj.get("title"),
                    "successor": {
                        "nickname": (succ or {}).get("nickname"),
                        "grade": (succ or {}).get("grade"),
                        "major": (succ or {}).get("major"),
                    },
                    "match_score": match.get("match_score") if match else None,
                    "match_reason_excerpt": (match.get("match_reason") or "")[:120] if match else None,
                    "awaken_votes": len(vote_rows),
                    "readiness": readiness,
                    "awakened_at": awaken.get("awakened_at"),
                    "stage_now": proj.get("stage"),
                })

            return {
                "source": "当前部署数据库实时聚合",
                "as_of": "请求时刻",
                "operational": {
                    "projects": len(projects),
                    "dormant_projects": len(dormant_ids),
                    "dormant_with_handover": covered,
                    "handover_coverage_pct": round(covered / len(dormant_ids) * 100) if dormant_ids else 0,
                    "awaken_records": len(awakens),
                    "story_records": len(stories),
                },
                "pilot": {
                    "status": f"两例真实续种试点已完成（项目{pilot_case_ids[0]}、{pilot_case_ids[1]}）",
                    "method": (
                        "确定性试点脚本 scripts/run_pilot_transfer.py 逐步执行：新人建档 → 六维可解释匹配 → "
                        "唤醒需求投票 → 三步确认（接棒意愿→原负责人核验授权→双方确认）→ 正式唤醒，"
                        "全程调用生产工具函数与库表校验，未使用任何模拟数据"
                    ),
                    "cases": cases,
                    "targets": [
                        "交接包资料可用率 ≥ 80%",
                        "接棒确认后 30 天仍有有效动态 ≥ 60%",
                        "接棒者首个里程碑完成率 ≥ 50%",
                    ],
                    "claim": (
                        "试点证明休眠项目可在真实系统内闭环完成「交接包核验 → 六维匹配 → 投票 → 唤醒」全流程；"
                        "长期传承有效性仍需跨届数据持续验证，以上目标为后续学期试点口径。"
                    ),
                },
            }

        try:
            return JSONResponse(await asyncio.to_thread(_query_evidence))
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] evidence query failed: %s", e)
            return JSONResponse({
                "source": "数据库暂不可用",
                "operational": {},
                "pilot": {"status": "试点数据暂不可用", "claim": "暂不展示未经核验的数据。"},
            })

    # --- 交接包全文展示：让评审/用户直接看到真实交接包，而非介绍 ---
    @app.get("/api/handover")
    async def api_handover(project_id: Optional[int] = None) -> JSONResponse:
        def _query_handover() -> Dict[str, Any]:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            if project_id is None:
                # 概览：所有已建档交接包的项目（附项目标题，便于前端直读）
                rows = (
                    client.table("fs_handover_packages")
                    .select("project_id, created_at, achievements, experience, pitfalls, remaining_issues, reusable_resources")
                    .order("project_id")
                    .execute()
                    .data
                    or []
                )
                proj_rows = (
                    client.table("fs_projects")
                    .select("id, title, stage")
                    .in_("id", sorted({int(r["project_id"]) for r in rows if r.get("project_id") is not None}))
                    .execute()
                    .data
                    or []
                )
                proj_map = {int(p["id"]): p for p in proj_rows}
                handovers = []
                for r in rows:
                    pid = int(r["project_id"])
                    proj = proj_map.get(pid, {})

                    def _cnt(key):
                        try:
                            import json as _json

                            val = r.get(key)
                            if isinstance(val, str):
                                val = _json.loads(val)
                            return len(val) if isinstance(val, list) else 0
                        except Exception:  # noqa: BLE001
                            return 0

                    handovers.append({
                        "project_id": pid,
                        "project_title": proj.get("title", f"项目 {pid}"),
                        "stage": proj.get("stage"),
                        "sections": {
                            "achievements": _cnt("achievements"),
                            "experience": _cnt("experience"),
                            "pitfalls": _cnt("pitfalls"),
                            "remaining_issues": _cnt("remaining_issues"),
                            "reusable_resources": _cnt("reusable_resources"),
                        },
                        "created_at": r.get("created_at"),
                    })
                return {"success": True, "mode": "overview", "handovers": handovers}
            row = (
                client.table("fs_handover_packages")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
                .data
            )
            if not row:
                return {"success": False, "message": f"项目 {project_id} 暂无交接包"}
            pkg = row[0]
            updates = (
                client.table("fs_project_updates")
                .select("content, created_at")
                .eq("project_id", project_id)
                .order("created_at", desc=False)
                .execute()
                .data
                or []
            )
            from tools.project_tools import assess_transfer_readiness

            readiness = assess_transfer_readiness(pkg, updates)
            return {
                "success": True,
                "mode": "detail",
                "project_id": project_id,
                "handover": pkg,
                "readiness": readiness,
                "update_count": len(updates),
            }

        try:
            return JSONResponse(await asyncio.to_thread(_query_handover))
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] handover query failed: %s", e)
            return JSONResponse({"success": False, "message": "交接包查询失败，请稍后再试"})

    # --- 传承扩展：故事墙 / 技能图谱 / 需求投票 / 排行榜 ---
    def _json_field(raw, default):
        if raw is None:
            return default
        if isinstance(raw, list):
            return raw
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else [str(raw)]
        except (json.JSONDecodeError, TypeError):
            return [str(raw)]

    def _count_tags(rows, field):
        counter: Dict[str, int] = {}
        for row in rows:
            for tag in _json_field(row.get(field), []):
                if tag and str(tag).strip():
                    key = str(tag).strip()
                    counter[key] = counter.get(key, 0) + 1
        return counter

    def _client():
        from storage.database.supabase_client import get_supabase_client

        return get_supabase_client()

    def _stories_query(limit: int = 24):
        client = _client()
        # v9.0 档案故事：基于真实公开报道、经艺术加工的传承故事（可点开看全文）
        curated_rows = client.table("fs_curated_stories").select(
            "id, title, school, era, tags, summary, story_full, source_url, source_name, is_featured, sort_no"
        ).order("sort_no", desc=False).limit(12).execute().data or []
        out = []
        for row in curated_rows:
            out.append({
                "kind": "archive",
                "id": 100000 + int(row["id"]),  # 前端区分档案故事点赞键
                "story_id": row["id"],
                "project_title": row["title"],
                "school": row.get("school"),
                "era": row.get("era"),
                "tags": _json_field(row.get("tags"), []),
                "summary": row.get("summary"),
                "story_full": row.get("story_full"),
                "source_url": row.get("source_url"),
                "source_name": row.get("source_name"),
                "is_featured": row.get("is_featured") or False,
                "founder_nickname": row.get("school") or "—",
                "successor_nickname": "档案故事",
                "story_text": row.get("summary") or "",
                "highlights": _json_field(row.get("tags"), [])[:3],
                "period_days": None,
                "likes": None,
            })
        rows = client.table("fs_stories").select(
            "id, project_id, project_title, founder_nickname, successor_nickname, "
            "match_reason, story_text, highlights, period_days, is_featured, likes, created_at"
        ).order("is_featured", desc=True).order("created_at", desc=True).limit(max(1, min(int(limit), 30))).execute()
        for row in (rows.data or []):
            row["kind"] = "awaken"
            row["highlights"] = _json_field(row.get("highlights"), [])
            out.append(row)
        return out

    @app.get("/api/stories")
    async def api_stories() -> JSONResponse:
        try:
            stories = await asyncio.to_thread(_stories_query)
            return JSONResponse({"stories": stories})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] stories query failed: %s", e)
            return JSONResponse({"stories": []})

    @app.get("/api/stories/{story_id}")
    async def api_story_detail(story_id: int) -> JSONResponse:
        """v9.0 档案故事详情（点开卡片看全文）"""
        try:
            row = await asyncio.to_thread(
                lambda: _client().table("fs_curated_stories")
                .select("id, title, school, era, tags, summary, story_full, source_url, source_name, is_featured")
                .eq("id", int(story_id))
                .maybe_single()
                .execute()
            )
            if not row or not row.data:
                return JSONResponse(status_code=404, content={"error": "故事不存在"})
            d = row.data
            d["tags"] = _json_field(d.get("tags"), [])
            return JSONResponse(d)
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] story detail failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.post("/api/stories/{story_id}/like")
    async def api_story_like(story_id: int) -> JSONResponse:
        def _like():
            client = _client()
            rows = client.table("fs_stories").select("likes").eq("id", int(story_id)).execute()
            current = (rows.data or [{}])[0].get("likes", 0) if rows.data else None
            if current is None:
                return None
            updated = client.table("fs_stories").update({"likes": int(current) + 1}).eq("id", int(story_id)).execute()
            return (updated.data or [{}])[0]

        try:
            row = await asyncio.to_thread(_like)
            if row is None:
                return JSONResponse(status_code=404, content={"error": "story not found"})
            return JSONResponse({"likes": row.get("likes", 0)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] story like failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    def _skills_query():
        client = _client()
        users = client.table("fs_users").select("skill_tags").execute().data or []
        projects = (
            client.table("fs_projects")
            .select("id, title, stage, required_skills")
            .execute().data or []
        )
        supply = _count_tags(users, "skill_tags")
        demand = _count_tags(projects, "required_skills")
        # v6.1 技能图谱大全：每个技能挂可参与的项目（已完成 fifth 与进行中/休眠均含）
        skill_projects: Dict[str, list] = {}
        stage_label = {
            "spring": "春·萌芽", "summer": "夏·生长", "autumn": "秋·沉淀",
            "winter": "冬·休眠", "fifth": "已完成·传承中",
        }
        for p in projects:
            for sk in p.get("required_skills") or []:
                skill_projects.setdefault(sk, []).append(
                    {"id": p["id"], "title": p["title"], "stage": stage_label.get(p.get("stage"), p.get("stage"))}
                )
        items = []
        for skill in set(supply) | set(demand) | set(skill_projects):
            sup, dem = supply.get(skill, 0), demand.get(skill, 0)
            items.append({
                "skill": skill, "supply": sup, "demand": dem, "gap": dem - sup,
                "status": "稀缺" if dem - sup > 0 else ("均衡" if sup == dem and dem > 0 else "富余"),
                "projects": sorted(skill_projects.get(skill, []), key=lambda x: x["id"])[:8],
            })
        items.sort(key=lambda x: (x["gap"], x["demand"]), reverse=True)
        return {"users": len(users), "projects": len(projects), "skills": items[:24]}

    @app.get("/api/skills")
    async def api_skills() -> JSONResponse:
        try:
            payload = await asyncio.to_thread(_skills_query)
            return JSONResponse(payload)
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] skills query failed: %s", e)
            return JSONResponse({"users": 0, "projects": 0, "skills": []})

    def _dormant_query(nickname: Optional[str] = None):
        from storage.database.supabase_client import get_supabase_client
        from tools.db_helpers import fetch_user_names, now_utc, parse_iso

        client = get_supabase_client()
        rows = client.table("fs_projects").select(
            "id, title, summary, hibernate_at, hibernate_reason, founder_id, domain_tags, required_skills"
        ).eq("stage", "winter").order("hibernate_at", desc=True).limit(60).execute().data or []
        votes = client.table("fs_votes").select("project_id, voter_nickname").execute().data or []
        vote_counts: Dict[int, int] = {}
        my_votes: set = set()
        for v in votes:
            vote_counts[v["project_id"]] = vote_counts.get(v["project_id"], 0) + 1
            if nickname and v.get("voter_nickname") == nickname:
                my_votes.add(v["project_id"])
        founder_ids = [r["founder_id"] for r in rows if r.get("founder_id")]
        names = fetch_user_names(founder_ids) if founder_ids else {}
        now = now_utc()
        out = []
        for r in rows:
            hib = parse_iso(r.get("hibernate_at") or "")
            days = max(0, (now - hib).days) if hib else None
            out.append({
                "id": r["id"], "title": r["title"], "summary": r.get("summary"),
                "hibernate_reason": r.get("hibernate_reason"), "dormant_days": days,
                "votes": vote_counts.get(r["id"], 0),
                "voted": r["id"] in my_votes,
                "founder_nickname": names.get(r.get("founder_id"), "—"),
                "domain_tags": _json_field(r.get("domain_tags"), []),
                "required_skills": _json_field(r.get("required_skills"), []),
            })
        out.sort(key=lambda x: x["votes"], reverse=True)
        return out

    @app.get("/api/dormant")
    async def api_dormant(request: Request) -> JSONResponse:
        try:
            # v7.0：登录后返回该用户的已投状态（未登录不报错，voted 恒为 false）
            nickname = _hdr_utf8(request.headers.get("X-FS-Nickname") or "").strip()
            if not nickname:
                cookie_raw = request.cookies.get("fs_auth") or ""
                if cookie_raw:
                    try:
                        from urllib.parse import unquote
                        cred = json.loads(unquote(cookie_raw))
                        nickname = str(cred.get("n") or "").strip()
                    except Exception:  # noqa: BLE001
                        nickname = ""
            items = await asyncio.to_thread(_dormant_query, nickname or None)
            return JSONResponse({"dormant": items})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] dormant query failed: %s", e)
            return JSONResponse({"dormant": []})

    def _vote_action(project_id: int, nickname: str):
        from storage.database.supabase_client import get_supabase_client
        from postgrest.exceptions import APIError

        client = get_supabase_client()
        nickname = (nickname or "").strip()
        if not nickname:
            raise ValueError("请先登录后再投票")
        found = safe_maybe_single(client.table("fs_users").select("id").eq("nickname", nickname))
        if not found:
            raise ValueError("昵称尚未建档：请先在对话页与知颜完成档案注册，再来投票（防刷票）")
        project = safe_maybe_single(client.table("fs_projects").select("id, title, stage").eq("id", int(project_id)))
        if not project:
            raise ValueError("项目不存在")
        if project.get("stage") != "winter":
            raise ValueError("该项目不在冬·蛰伏阶段，暂无需唤醒投票")
        try:
            client.table("fs_votes").insert({"project_id": int(project_id), "voter_nickname": nickname}).execute()
            action = "voted"
        except APIError as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                action = "duplicated"
            else:
                raise
        votes = client.table("fs_votes").select("id").eq("project_id", int(project_id)).execute()
        return {"action": action, "project_id": int(project_id), "title": project.get("title"), "votes": len(votes.data or [])}

    @app.post("/api/votes")
    async def api_votes(request: Request) -> JSONResponse:
        try:
            # v7.0：投票身份取自登录态（请求头），不再信任 body 里的昵称
            user = await asyncio.to_thread(_auth_user, request)
            body = await request.json()
            payload = await asyncio.to_thread(
                _vote_action, int((body or {}).get("project_id") or 0), user["nickname"]
            )
            return JSONResponse(payload)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] vote failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.get("/api/leaderboard")
    async def api_leaderboard(request: Request) -> JSONResponse:
        try:
            full = str((request.query_params or {}).get("full") or "") in ("1", "true", "yes")
            from tools.legacy_tools import compute_all_user_points, POINT_RULES

            ranked = await asyncio.to_thread(compute_all_user_points)
            if full:
                # v9.0 完整风云榜：含积分规则与画像公开标记（画像内容仍走 /api/profile/{nickname} 鉴权）
                return JSONResponse({"leaderboard": ranked[:50], "rules": POINT_RULES})
            return JSONResponse({"leaderboard": ranked[:5]})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] leaderboard query failed: %s", e)
            return JSONResponse({"leaderboard": []})

    # --- v6.2 项目引入模块：详情 / 关键词搜索 / 引入接棒 ---

    def _project_search_query(q: str, limit: int = 12):
        from storage.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        keyword = (q or "").strip()
        if not keyword:
            raise ValueError("请输入关键词，例如项目名、领域或技能")
        like = f"%{keyword}%"
        _fields = "id,title,summary,stage,domain_tags,required_skills,founder_id,hibernate_reason,school,source_url,source_name"
        rows = (
            client.table("fs_projects")
            .select(_fields)
            .or_(f"title.ilike.{like},summary.ilike.{like}")
            .order("id", desc=False)
            .limit(limit)
            .execute()
        )
        items = list(rows.data or [])
        if not items:
            all_rows = (
                client.table("fs_projects")
                .select(_fields)
                .order("id", desc=False)
                .execute()
            )
            for p in (all_rows.data or []):
                blob = " ".join(
                    str(p.get(k) or "") for k in ("title", "summary", "domain_tags", "required_skills")
                )
                if keyword.lower() in blob.lower():
                    items.append(p)
                    if len(items) >= limit:
                        break
        # v7.0 优先级排序：本校项目优先 → 有交接包（建档过）优先 → 原顺序
        handover_pids = set(
            r["project_id"] for r in (client.table("fs_handover_packages").select("project_id").execute().data or [])
        )
        items.sort(key=lambda p: (
            0 if p.get("school") == "南京大学" else 1,
            0 if p.get("id") in handover_pids else 1,
        ))
        for p in items:
            uid = p.pop("founder_id", None)
            if uid is not None:
                u = safe_maybe_single(client.table("fs_users").select("nickname").eq("id", int(uid)))
                p["founder_nickname"] = (u or {}).get("nickname") or "—"
            else:
                p["founder_nickname"] = "—"
            p["has_handover"] = p.get("id") in handover_pids
        return items

    @app.get("/api/projects/search")
    async def api_project_search(q: str = "", limit: int = 12) -> JSONResponse:
        try:
            items = await asyncio.to_thread(_project_search_query, q, int(limit))
            return JSONResponse({"items": items})
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] project search failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    def _project_import_action(project_id: int, nickname: str):
        from storage.database.supabase_client import get_supabase_client
        from postgrest.exceptions import APIError

        client = get_supabase_client()
        nickname = (nickname or "").strip()
        if not nickname:
            raise ValueError("引入前请先输入你的昵称")
        u = safe_maybe_single(client.table("fs_users").select("id,nickname").eq("nickname", nickname))
        user = u or {}
        if not user:
            raise ValueError("昵称尚未建档：请先在对话页与知颜完成档案注册，再引入项目")
        project = safe_maybe_single(client.table("fs_projects").select("id,title,stage,founder_id").eq("id", int(project_id)))
        if not project:
            raise ValueError("项目不存在")
        if int(project.get("founder_id") or 0) == int(user.get("id") or 0):
            raise ValueError("这是你自己发起的项目，无需引入")
        try:
            client.table("fs_project_members").insert({
                "project_id": int(project_id),
                "user_id": int(user["id"]),
                "role": "接棒人",
            }).execute()
            action = "imported"
        except APIError as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                action = "duplicated"
            else:
                raise
        members = client.table("fs_project_members").select("id").eq("project_id", int(project_id)).execute()
        return {
            "action": action,
            "project_id": int(project_id),
            "title": project.get("title"),
            "nickname": nickname,
            "members": len(members.data or []),
        }

    @app.post("/api/projects/import")
    async def api_project_import(request: Request) -> JSONResponse:
        try:
            # v7.0：引入身份取自登录态（请求头）
            user = await asyncio.to_thread(_auth_user, request)
            payload = await asyncio.to_thread(
                _project_import_action,
                int(((await request.json()) or {}).get("project_id") or 0),
                user["nickname"],
            )
            return JSONResponse(payload)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] project import failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    def _project_detail_query(project_id: int, viewer: Optional[dict] = None):
        from storage.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        project = safe_maybe_single(client.table("fs_projects").select(
            "id,title,summary,stage,domain_tags,required_skills,"
            "founder_id,owner_id,hibernate_reason,created_at,school,source_url,source_name,handover_public"
        ).eq("id", int(project_id)))
        if not project:
            raise ValueError("项目不存在")

        for uid_field, nickname_field in (("founder_id", "founder_nickname"), ("owner_id", "owner_nickname")):
            uid = project.get(uid_field)
            if uid is None:
                project[nickname_field] = "—"
                continue
            u = safe_maybe_single(client.table("fs_users").select("nickname").eq("id", int(uid)))
            project[nickname_field] = (u or {}).get("nickname") or "—"

        pkg_rows = client.table("fs_handover_packages").select(
            "achievements,experience,pitfalls,remaining_issues,reusable_resources,created_at"
        ).eq("project_id", int(project_id)).order("created_at", desc=True).limit(1).execute()
        pkg = (pkg_rows.data or [None])[0] if (pkg_rows.data or []) else None

        def _to_list(v):
            if isinstance(v, list):
                return v
            if isinstance(v, str) and v.strip():
                import json as _json
                try:
                    parsed = _json.loads(v)
                    return parsed if isinstance(parsed, list) else [v]
                except (ValueError, TypeError):
                    return [seg.strip() for seg in v.split(",") if seg.strip()]
            return []

        if pkg:
            for k in ("achievements", "experience", "pitfalls", "remaining_issues", "reusable_resources"):
                pkg[k] = _to_list(pkg.get(k))
            # 治理三声明以「【授权范围】/【资源有效期】/【原团队权益】」前缀拼在 reusable_resources 内
            gov = {}
            resources = []
            for item in list(pkg.get("reusable_resources") or []):
                text = str(item)
                if text.startswith("【授权范围】"):
                    gov["authorization_scope"] = text.replace("【授权范围】", "", 1).strip()
                elif text.startswith("【资源有效期】"):
                    gov["resource_valid_until"] = text.replace("【资源有效期】", "", 1).strip()
                elif text.startswith("【原团队权益】"):
                    gov["founder_rights"] = text.replace("【原团队权益】", "", 1).strip()
                else:
                    resources.append(item)
            pkg["reusable_resources"] = resources
            pkg["authorization_scope"] = gov.get("authorization_scope", "")
            pkg["resource_valid_until"] = gov.get("resource_valid_until", "")
            pkg["founder_rights"] = gov.get("founder_rights", "")

        members_rows = client.table("fs_project_members").select(
            "user_id,role,joined_at"
        ).eq("project_id", int(project_id)).order("joined_at", desc=False).execute()
        members = []
        for m in (members_rows.data or []):
            u = safe_maybe_single(client.table("fs_users").select("nickname").eq("id", int(m.get("user_id") or 0)))
            members.append({
                "nickname": (u or {}).get("nickname") or "—",
                "role": m.get("role") or "成员",
                "joined_note": "",
                "joined_at": m.get("joined_at") or "",
            })

        # v10.0 交接包授权：未公开（handover_public=false）时，仅发起人/现任负责人可查看
        handover_locked = False
        if pkg and not project.get("handover_public"):
            viewer_id = int((viewer or {}).get("id") or 0)
            if viewer_id not in (int(project.get("founder_id") or 0), int(project.get("owner_id") or 0)):
                handover_locked = True
                pkg = None
        return {"project": project, "handover": pkg, "members": members, "handover_locked": handover_locked}

    @app.get("/api/projects/{project_id}")
    async def api_project_detail(project_id: int, request: Request) -> JSONResponse:
        try:
            viewer = None
            try:
                viewer = await asyncio.to_thread(_auth_user, request)
            except PermissionError:
                viewer = None
            payload = await asyncio.to_thread(_project_detail_query, int(project_id), viewer)
            return JSONResponse(payload)
        except ValueError as e:
            return JSONResponse(status_code=404, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] project detail failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    # ==================== v10.0 引入卡删除 ====================
    @app.delete("/api/projects/{project_id}/unimport")
    async def api_project_unimport(project_id: int, request: Request) -> JSONResponse:
        """从我的种子库移除已引入的公开种子卡（不删项目本身）"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            from storage.database.supabase_client import get_supabase_client

            def _del(client):
                resp = (
                    client.table("fs_project_members")
                    .delete()
                    .eq("project_id", int(project_id))
                    .eq("user_id", int(auth_user["id"]))
                    .execute()
                )
                return len(rows_of(resp))

            client = get_supabase_client()
            removed = await asyncio.to_thread(_del, client)
            if not removed:
                return JSONResponse(status_code=404, content={"error": "未找到你引入的这张种子卡"})
            return JSONResponse({"success": True, "removed": removed})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] project unimport failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    # ==================== v10.0 团队空间：对话记录互相可见 ====================
    def _team_chat_history(client, tid: int) -> list:
        rows = rows_of(
            client.table("fs_team_chat_messages")
            .select("id, user_id, nickname, role, content, created_at")
            .eq("team_id", int(tid))
            .order("created_at", desc=False)
            .limit(300)
            .execute()
        )
        return [
            {
                "user_id": r.get("user_id"),
                "nickname": r.get("nickname") or "—",
                "role": r.get("role") or "member",
                "content": r.get("content") or "",
                "created_at": r.get("created_at"),
            }
            for r in rows
        ]

    @app.get("/api/teams/{tid}/chat")
    async def api_team_chat(tid: int, request: Request) -> JSONResponse:
        """团队空间共享对话历史（全员互相可见）"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            from storage.database.supabase_client import get_supabase_client

            def _query(client):
                team = safe_maybe_single(
                    client.table("fs_teams").select("id, leader_id").eq("id", int(tid))
                )
                if not team:
                    raise ValueError("团队不存在")
                m = safe_maybe_single(
                    client.table("fs_team_members").select("role, status")
                    .eq("team_id", int(tid)).eq("user_id", int(auth_user["id"]))
                )
                if not ((m and m.get("status") == "approved") or team["leader_id"] == auth_user["id"]):
                    raise PermissionError("你还不是该团队成员")
                return _team_chat_history(client, int(tid))

            client = get_supabase_client()
            history = await asyncio.to_thread(_query, client)
            return JSONResponse({"messages": history})
        except PermissionError as e:
            return JSONResponse(status_code=403, content={"error": str(e)})
        except ValueError as e:
            return JSONResponse(status_code=404, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] team chat history failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    # ==================== v10.0 成员间留言（复用留言信箱） ====================
    @app.post("/api/messages/send")
    async def api_message_send(request: Request) -> JSONResponse:
        """给指定用户（如团队成员）留言：复用 fs_messages 信箱"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            body = await request.json() or {}
            to_nickname = str(body.get("to") or "").strip()
            content = str(body.get("content") or "").strip()
            if not to_nickname or not content:
                return JSONResponse(status_code=400, content={"error": "请填写收件人与留言内容"})
            if len(content) > 500:
                content = content[:500]

            from storage.database.supabase_client import get_supabase_client

            def _send(client):
                target = safe_maybe_single(
                    client.table("fs_users").select("id, nickname").eq("nickname", to_nickname)
                )
                if not target:
                    raise ValueError(f"未找到用户「{to_nickname}」")
                if int(target["id"]) == int(auth_user["id"]):
                    raise ValueError("不能给自己留言哦")
                client.table("fs_messages").insert({
                    "sender_id": int(auth_user["id"]),
                    "receiver_id": int(target["id"]),
                    "content": content,
                }).execute()
                return target["nickname"]

            client = get_supabase_client()
            to_name = await asyncio.to_thread(_send, client)
            return JSONResponse({"success": True, "to": to_name})
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] message send failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    # ==================== v10.0 个人项目库 ====================
    def _my_projects(client, uid: int) -> list:
        rows = rows_of(
            client.table("fs_personal_projects")
            .select("id, title, summary, description, status, source_project_id, tags, handover_package, handover_public, created_at, updated_at")
            .eq("user_id", int(uid))
            .order("updated_at", desc=True)
            .limit(100)
            .execute()
        )
        items = []
        for r in rows:
            r = dict(r)
            pkg = r.get("handover_package")
            if isinstance(pkg, str) and pkg.strip():
                try:
                    pkg = json.loads(pkg)
                except (ValueError, TypeError):
                    pkg = None
            r["handover_package"] = pkg if isinstance(pkg, dict) else None
            r["has_handover"] = bool(pkg)
            items.append(r)
        return items

    @app.get("/api/my-projects")
    async def api_my_projects(request: Request) -> JSONResponse:
        """个人项目库：仅本人可见，包含完整项目信息与交接包"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            projects = await asyncio.to_thread(_my_projects, client, auth_user["id"])
            return JSONResponse({"projects": projects, "total": len(projects)})
        except Exception as e:  # noqa: BLE001
            logger.exception("[my_projects] failed")
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.post("/api/my-projects")
    async def api_my_project_create(request: Request) -> JSONResponse:
        """在个人项目库新建项目（未完成 / 接棒中均可）"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            body = await request.json() or {}
            title = str(body.get("title") or "").strip()
            if not title:
                return JSONResponse(status_code=400, content={"error": "请填写项目名称"})
            status = str(body.get("status") or "ongoing")
            if status not in ("ongoing", "unfinished", "taken_over", "done"):
                status = "ongoing"
            from storage.database.supabase_client import get_supabase_client

            def _insert(client):
                row = {
                    "user_id": int(auth_user["id"]),
                    "title": title[:80],
                    "summary": str(body.get("summary") or "").strip()[:200],
                    "description": str(body.get("description") or "").strip()[:4000],
                    "status": status,
                    "source_project_id": body.get("source_project_id"),
                    "tags": [str(t)[:20] for t in (body.get("tags") or [])][:8],
                }
                resp = client.table("fs_personal_projects").insert(row).execute()
                return (rows_of(resp) or [{}])[0]

            client = get_supabase_client()
            created = await asyncio.to_thread(_insert, client)
            return JSONResponse({"success": True, "project": created})
        except Exception as e:  # noqa: BLE001
            logger.warning("[my_projects] create failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.patch("/api/my-projects/{pid}")
    async def api_my_project_update(pid: int, request: Request) -> JSONResponse:
        """更新个人项目（信息 / 状态 / 交接包公开开关）"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            body = await request.json() or {}
            from storage.database.supabase_client import get_supabase_client

            def _update(client):
                patch: Dict[str, Any] = {"updated_at": datetime.now().isoformat(timespec="seconds")}
                for key, maxlen in (("title", 80), ("summary", 200), ("description", 4000)):
                    if key in body:
                        patch[key] = str(body.get(key) or "").strip()[:maxlen]
                if "status" in body and str(body["status"]) in ("ongoing", "unfinished", "taken_over", "done"):
                    patch["status"] = str(body["status"])
                if "tags" in body and isinstance(body["tags"], list):
                    patch["tags"] = [str(t)[:20] for t in body["tags"]][:8]
                if "handover_public" in body:
                    patch["handover_public"] = bool(body["handover_public"])
                resp = (
                    client.table("fs_personal_projects")
                    .update(patch)
                    .eq("id", int(pid))
                    .eq("user_id", int(auth_user["id"]))
                    .execute()
                )
                rows = rows_of(resp)
                if not rows:
                    return None
                row = dict(rows[0])
                pkg = row.get("handover_package")
                if isinstance(pkg, str) and pkg.strip():
                    try:
                        pkg = json.loads(pkg)
                    except (ValueError, TypeError):
                        pkg = None
                row["handover_package"] = pkg if isinstance(pkg, dict) else None
                row["has_handover"] = bool(pkg)
                return row

            client = get_supabase_client()
            row = await asyncio.to_thread(_update, client)
            if not row:
                return JSONResponse(status_code=404, content={"error": "项目不存在或无权修改"})
            return JSONResponse({"success": True, "project": row})
        except Exception as e:  # noqa: BLE001
            logger.warning("[my_projects] update failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.delete("/api/my-projects/{pid}")
    async def api_my_project_delete(pid: int, request: Request) -> JSONResponse:
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            from storage.database.supabase_client import get_supabase_client

            def _del(client):
                resp = (
                    client.table("fs_personal_projects")
                    .delete()
                    .eq("id", int(pid))
                    .eq("user_id", int(auth_user["id"]))
                    .execute()
                )
                return len(rows_of(resp))

            client = get_supabase_client()
            removed = await asyncio.to_thread(_del, client)
            if not removed:
                return JSONResponse(status_code=404, content={"error": "项目不存在"})
            return JSONResponse({"success": True})
        except Exception as e:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.get("/api/handover/personal/{pid}")
    async def api_personal_handover(pid: int) -> JSONResponse:
        """公开的个人项目交接包（handover_public=true 时任何人可获取）"""
        try:
            from storage.database.supabase_client import get_supabase_client

            def _query(client):
                row = safe_maybe_single(
                    client.table("fs_personal_projects")
                    .select("id, title, summary, tags, handover_package, handover_public, user_id, updated_at")
                    .eq("id", int(pid))
                )
                if not row:
                    raise ValueError("项目不存在")
                if not row.get("handover_public"):
                    raise PermissionError("该项目尚未公开交接包")
                pkg = row.get("handover_package")
                if isinstance(pkg, str) and pkg.strip():
                    try:
                        pkg = json.loads(pkg)
                    except (ValueError, TypeError):
                        pkg = None
                owner = safe_maybe_single(
                    client.table("fs_users").select("nickname").eq("id", int(row["user_id"]))
                )
                return {
                    "project": {
                        "id": row["id"],
                        "title": row["title"],
                        "summary": row.get("summary"),
                        "tags": row.get("tags") or [],
                        "fs_code": f"PJ-{int(row['id']):03d}",
                        "owner_nickname": (owner or {}).get("nickname") or "—",
                        "updated_at": row.get("updated_at"),
                    },
                    "handover": pkg,
                }

            client = get_supabase_client()
            payload = await asyncio.to_thread(_query, client)
            return JSONResponse(payload)
        except PermissionError as e:
            return JSONResponse(status_code=403, content={"error": str(e)})
        except ValueError as e:
            return JSONResponse(status_code=404, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("[web] personal handover failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    # --- SSE 流式对话 ---
    # ==================== v8.0 种子卡生态：种子库 / 上传 / 团队 / 画像 ====================

    def _my_seed_cards(client, uid: int, legacy_code: str) -> list:
        rows = rows_of(
            client.table("fs_inspirations")
            .select("id, title, tags, content, status, project_id, created_at")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        items = []
        for r in rows:
            r = dict(r)
            r["seed_code"] = f"{legacy_code}-{int(r['id']):03d}"
            items.append(r)
        return items

    @app.get("/api/seeds/mine")
    async def api_seeds_mine(request: Request):
        """我的个人种子库（个人种子卡 + 我引入的公开种子卡）"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            lc_rows = rows_of(
                client.table("fs_users").select("legacy_code").eq("id", auth_user["id"]).execute()
            )
            legacy_code = (lc_rows[0] or {}).get("legacy_code") or "000000"
            seeds = _my_seed_cards(client, auth_user["id"], legacy_code)
            # v9.0 引入的公开种子卡（fs_project_members：把项目带进自己的种子库）
            imported = []
            try:
                imp_rows = rows_of(
                    client.table("fs_project_members")
                    .select("project_id, role, joined_at")
                    .eq("user_id", auth_user["id"])
                    .order("joined_at", desc=True)
                    .limit(50)
                    .execute()
                )
                pids = [r["project_id"] for r in imp_rows]
                vote_counts: Dict[int, int] = {}
                if pids:
                    v_rows = rows_of(
                        client.table("fs_votes").select("project_id").in_("project_id", pids).execute()
                    )
                    for v in v_rows:
                        vote_counts[v["project_id"]] = vote_counts.get(v["project_id"], 0) + 1
                    p_rows = rows_of(
                        client.table("fs_projects")
                        .select("id, title, summary, domain_tags, stage, school")
                        .in_("id", pids)
                        .execute()
                    )
                    p_map = {p["id"]: p for p in p_rows}
                    for r in imp_rows:
                        p = p_map.get(r["project_id"])
                        if not p:
                            continue
                        imported.append({
                            "project_id": r["project_id"],
                            "fs_code": f"FS-{int(r['project_id']):03d}",
                            "title": p.get("title"),
                            "summary": (p.get("summary") or "")[:120],
                            "domain_tags": _json_field(p.get("domain_tags"), [])[:3],
                            "school": p.get("school"),
                            "role": r.get("role") or "接棒人",
                            "votes": vote_counts.get(r["project_id"], 0),
                            "created_at": r.get("joined_at"),
                        })
            except Exception as e:  # noqa: BLE001
                logger.warning("[seeds_mine] imported query failed: %s", e)
            return {
                "seeds": seeds,
                "imported": imported,
                "legacy_code_prefix": legacy_code,
                "total": len(seeds),
                "imported_total": len(imported),
            }
        except Exception as e:  # noqa: BLE001
            logger.exception("[seeds_mine] failed")
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.delete("/api/seeds/{sid}")
    async def api_seed_delete(sid: int, request: Request):
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            resp = (
                client.table("fs_inspirations")
                .delete()
                .eq("id", sid)
                .eq("user_id", auth_user["id"])
                .execute()
            )
            if not rows_of(resp):
                return JSONResponse(status_code=404, content={"error": "种子卡不存在"})
            return {"success": True}
        except Exception as e:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.get("/api/seeds/public")
    async def api_seeds_public():
        """公开种子库：所有项目即公开种子卡（编号 FS-#N），按更新时间倒序"""
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            projects = rows_of(
                client.table("fs_projects")
                .select(
                    "id, title, summary, domain_tags, required_skills, stage, "
                    "school, source_name, source_url, owner_id, updated_at, created_at, handover_public"
                )
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            hp = {
                h["project_id"]
                for h in rows_of(
                    client.table("fs_handover_packages").select("project_id").execute()
                )
            }
            votes = {}
            for v in rows_of(client.table("fs_votes").select("project_id").execute()):
                votes[v["project_id"]] = votes.get(v["project_id"], 0) + 1
            owners = {}
            if projects:
                oids = list({p["owner_id"] for p in projects})
                for u in rows_of(
                    client.table("fs_users")
                    .select("id, nickname, profile_public, persona")
                    .in_("id", oids)
                    .execute()
                ):
                    owners[u["id"]] = u
            items = []
            for p in projects:
                o = owners.get(p["owner_id"], {})
                items.append(
                    {
                        "id": p["id"],
                        "fs_code": f"FS-{p['id']:03d}",
                        "title": p["title"],
                        "summary": p["summary"],
                        "domain_tags": p.get("domain_tags") or [],
                        "required_skills": p.get("required_skills") or [],
                        "stage": p["stage"],
                        "school": p.get("school"),
                        "source_name": p.get("source_name"),
                        "source_url": p.get("source_url"),
                        "has_handover": p["id"] in hp,
                        "handover_public": bool(p.get("handover_public")),
                        "votes": votes.get(p["id"], 0),
                        "owner_nickname": o.get("nickname"),
                        "owner_profile_public": bool(o.get("profile_public")),
                        "kind": "fs",
                    }
                )
            # v10.0 需求需求⑦⑧：个人项目库中公开交接包的项目（PJ-#N）也进入公开种子库
            try:
                personal = rows_of(
                    client.table("fs_personal_projects")
                    .select("id, title, summary, tags, user_id, updated_at, handover_package")
                    .eq("handover_public", True)
                    .order("updated_at", desc=True)
                    .limit(50)
                    .execute()
                )
                p_owner_ids = list({q["user_id"] for q in personal})
                p_owners = {
                    u["id"]: u.get("nickname")
                    for u in rows_of(
                        client.table("fs_users").select("id, nickname").in_("id", p_owner_ids).execute()
                    )
                } if p_owner_ids else {}
                for q in personal:
                    pkg = q.get("handover_package")
                    if isinstance(pkg, str) and pkg.strip():
                        try:
                            pkg = json.loads(pkg)
                        except (ValueError, TypeError):
                            pkg = None
                    items.append(
                        {
                            "id": int(q["id"]),
                            "fs_code": f"PJ-{int(q['id']):03d}",
                            "title": q["title"],
                            "summary": q.get("summary") or "",
                            "domain_tags": (q.get("tags") or [])[:4],
                            "required_skills": [],
                            "stage": "personal",
                            "school": None,
                            "source_name": "个人项目库",
                            "source_url": None,
                            "has_handover": bool(pkg),
                            "handover_public": True,
                            "votes": 0,
                            "owner_nickname": p_owners.get(q["user_id"], "—"),
                            "owner_profile_public": False,
                            "kind": "personal",
                        }
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("[seeds_public] personal merge failed: %s", e)
            return {"seeds": items, "total": len(items)}
        except Exception as e:  # noqa: BLE001
            logger.exception("[seeds_public] failed")
            return JSONResponse(status_code=500, content={"error": str(e)})

    def _parse_uploaded_file(filename: str, data: bytes) -> str:
        ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
        if ext in ("txt", "md", "csv", "json", "py", "js", "ts", "html", "css", "sql", "yml", "yaml", "log", "xml", "ini", "toml"):
            return data.decode("utf-8", errors="replace")
        if ext == "pdf":
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages[:50])
        if ext == "docx":
            import io

            from docx2python import docx2python

            doc = docx2python(io.BytesIO(data))
            return str(doc.text)[:80000]
        raise ValueError(f"暂不支持 .{ext} 文件（支持 txt/md/csv/json/代码文件/pdf/docx）")

    @app.post("/api/upload")
    async def api_upload(request: Request):
        """上传文件 → 解析为纯文本 → 登记到 /tmp/fs_uploads，返回 file_id 供知颜 read_upload 读取"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            from starlette.datastructures import UploadFile as _StarletteUploadFile

            form = await request.form()
            file = form.get("file")
            # 注意：form 解析返回 starlette 的 UploadFile（fastapi 的是其子类，反查会 False）
            if not isinstance(file, _StarletteUploadFile):
                return JSONResponse(status_code=400, content={"error": "缺少文件字段 file"})
            data = await file.read()
            if len(data) > 15 * 1024 * 1024:
                return JSONResponse(status_code=400, content={"error": "文件过大（上限 15MB）"})
            filename = file.filename or "upload.txt"
            text = _parse_uploaded_file(filename, data)
            import secrets

            file_id = f"up_{secrets.token_hex(4)}"
            os.makedirs("/tmp/fs_uploads", exist_ok=True)
            with open(f"/tmp/fs_uploads/{file_id}.json", "w", encoding="utf-8") as f:
                json.dump(
                    {"name": filename, "type": filename.rsplit('.', 1)[-1].lower(), "chars": len(text), "content": text[:120000], "owner": auth_user["id"]},
                    f,
                    ensure_ascii=False,
                )
            return {
                "success": True,
                "file_id": file_id,
                "file_name": filename,
                "chars": len(text),
                "preview": text[:120],
                "hint": "文件已解析，请在对话中让知颜整理建档（知颜会读取全文）",
            }
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.exception("[upload] failed")
            return JSONResponse(status_code=500, content={"error": f"上传解析失败：{e}"})

    # ---------- 组队空间 ----------

    def _team_with_members(client, team_id: int) -> Optional[dict]:
        team = safe_maybe_single(client.table("fs_teams").select("*").eq("id", team_id))
        if not team:
            return None
        members = rows_of(
            client.table("fs_team_members")
            .select("id, user_id, role, status, note, applied_at")
            .eq("team_id", team_id)
            .order("applied_at", desc=False)
            .execute()
        )
        uids = list({m["user_id"] for m in members} | {team["leader_id"]})
        umap = {
            u["id"]: u
            for u in rows_of(
                client.table("fs_users")
                .select("id, nickname, grade, major, skill_tags, persona, profile_public")
                .in_("id", uids)
                .execute()
            )
        }
        leader = umap.get(team["leader_id"], {})
        member_list = []
        for m in members:
            u = umap.get(m["user_id"], {})
            persona_txt = ""
            if u.get("profile_public") and u.get("persona"):
                p = u["persona"]
                p = p if isinstance(p, dict) else json.loads(p)
                persona_txt = "；".join(f"{k}：{v}" for k, v in p.items() if v and k in ("traits", "strengths"))[:120]
            member_list.append(
                {
                    "user_id": m["user_id"],
                    "nickname": u.get("nickname"),
                    "grade": u.get("grade"),
                    "major": u.get("major"),
                    "skills": (u.get("skill_tags") or [])[:6],
                    "role": m["role"],
                    "status": m["status"],
                    "note": (m.get("note") or "")[:120],
                    "persona_public": persona_txt,
                    "applied_at": m.get("applied_at"),
                }
            )
        project = None
        if team.get("project_id"):
            project = safe_maybe_single(
                client.table("fs_projects")
                .select("id, title, summary, domain_tags, required_skills, stage, updated_at, handover_public")
                .eq("id", team["project_id"])
            )
        return {
            "id": team["id"],
            "name": team["name"],
            "description": team.get("description"),
            "poster_url": team.get("poster_url"),
            "leader_id": team["leader_id"],
            "leader_nickname": leader.get("nickname"),
            "leader_grade": leader.get("grade"),
            "leader_major": leader.get("major"),
            "leader_persona_public": (leader.get("persona") or "") if leader.get("profile_public") else "",
            "project_id": team.get("project_id"),
            "project": project,
            "status": team.get("status"),
            "created_at": team.get("created_at"),
            "members": member_list,
        }

    @app.post("/api/teams")
    async def api_team_create(request: Request):
        """建队：队长把公开种子卡（项目）或招募海报上传到组队空间并招募"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid JSON"})
        name = str((body or {}).get("name") or "").strip()
        description = str((body or {}).get("description") or "").strip()
        project_id = (body or {}).get("project_id")
        poster = str((body or {}).get("poster") or "").strip()
        if not name or len(name) > 40:
            return JSONResponse(status_code=400, content={"error": "队名必填（1-40字）"})
        if project_id is not None:
            project_id = int(project_id)
        # v9.0 招募海报：base64 data URL（图片，≤2.5MB 解码后）
        poster_url = None
        if poster:
            if not poster.startswith("data:image/"):
                return JSONResponse(status_code=400, content={"error": "海报仅支持图片文件（png/jpg/webp/gif）"})
            try:
                b64 = poster.split(",", 1)[1] if "," in poster else ""
                import base64 as _b64
                if len(_b64.b64decode(b64, validate=False)) > 2_500_000:
                    return JSONResponse(status_code=400, content={"error": "海报图片过大（≤2.5MB）"})
            except Exception:
                return JSONResponse(status_code=400, content={"error": "海报图片解析失败"})
            poster_url = poster
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            resp = (
                client.table("fs_teams")
                .insert(
                    {
                        "name": name,
                        "description": description[:500] if description else None,
                        "leader_id": auth_user["id"],
                        "project_id": project_id,
                        "poster_url": poster_url,
                        "status": "recruiting",
                    }
                )
                .execute()
            )
            team = rows_of(resp)[0]
            client.table("fs_team_members").insert(
                {"team_id": team["id"], "user_id": auth_user["id"], "role": "leader", "status": "approved"}
            ).execute()
            return {"success": True, "team": _team_with_members(client, team["id"])}
        except Exception as e:  # noqa: BLE001
            logger.exception("[team_create] failed")
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.get("/api/teams")
    async def api_teams_list(request: Request):
        """组队空间：招募中团队列表 + 我的团队与申请状态。

        v9.0：招募区对未登录访客也开放（需求「所有用户可见」）——
        匿名请求返回招募列表，my_teams 为空。
        """
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError:
            auth_user = None  # 匿名访客：可浏览招募区，看不到「我的团队」
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            recruiting = rows_of(
                client.table("fs_teams")
                .select("id, name, description, leader_id, project_id, poster_url, status, created_at")
                .eq("status", "recruiting")
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )
            my_rows = rows_of(
                client.table("fs_team_members")
                .select("team_id, role, status")
                .eq("user_id", int(auth_user["id"]))
                .execute()
            ) if auth_user else []
            my_map = {m["team_id"]: m for m in my_rows}
            all_ids = list({t["id"] for t in recruiting} | set(my_map.keys()))
            details = {t["id"]: t for t in (await asyncio.to_thread(_teams_bulk, client, all_ids)) if t}
            items = []
            for t in recruiting:
                d = details.get(t["id"]) or {}
                approved = [m for m in d.get("members", []) if m["status"] == "approved"]
                mine = my_map.get(t["id"])
                items.append(
                    {
                        "id": t["id"],
                        "name": t["name"],
                        "description": t.get("description"),
                        "poster_url": t.get("poster_url"),
                        "status": t["status"],
                        "leader_nickname": d.get("leader_nickname"),
                        "project": d.get("project"),
                        "member_count": len(approved) + 1,
                        "my_role": (mine or {}).get("role"),
                        "my_status": (mine or {}).get("status"),
                    }
                )
            my_teams = []
            for tid, m in my_map.items():
                d = details.get(tid) or {}
                my_teams.append(
                    {
                        "id": tid,
                        "name": d.get("name") or f"团队#{tid}",
                        "role": "队长" if m["role"] == "leader" else "成员",
                        "status": m["status"],
                        "team_status": d.get("status"),
                        "poster_url": d.get("poster_url"),
                        "member_count": len([x for x in d.get("members", []) if x["status"] == "approved"]) + 1,
                    }
                )
            return {"teams": items, "my_teams": my_teams}
        except Exception as e:  # noqa: BLE001
            logger.exception("[teams_list] failed")
            return JSONResponse(status_code=500, content={"error": str(e)})

    def _teams_bulk(client, team_ids: list) -> list:
        if not team_ids:
            return []
        return [_team_with_members(client, tid) for tid in team_ids]

    @app.get("/api/teams/{tid}")
    async def api_team_detail(tid: int, request: Request):
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            team = _team_with_members(client, tid)
            if not team:
                return JSONResponse(status_code=404, content={"error": "团队不存在"})
            mine = safe_maybe_single(
                client.table("fs_team_members")
                .select("role, status")
                .eq("team_id", tid)
                .eq("user_id", auth_user["id"])
            )
            team["my_role"] = (mine or {}).get("role")
            team["my_status"] = (mine or {}).get("status")
            team["is_leader"] = team["leader_id"] == auth_user["id"]
            if not team["is_leader"]:
                team["members"] = [m for m in team["members"] if m["status"] == "approved"] or []
            return team
        except Exception as e:  # noqa: BLE001
            logger.exception("[team_detail] failed")
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.post("/api/teams/{tid}/apply")
    async def api_team_apply(tid: int, request: Request):
        """申请加入团队 → 队长信箱自动收到申请留言（含申请人画像摘要-if公开）"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            body = await request.json()
            note = str((body or {}).get("note") or "").strip()
        except Exception:
            note = ""
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            team = safe_maybe_single(client.table("fs_teams").select("id, name, leader_id, status").eq("id", tid))
            if not team:
                return JSONResponse(status_code=404, content={"error": "团队不存在"})
            if team.get("status") != "recruiting":
                return JSONResponse(status_code=400, content={"error": "该团队已停止招募"})
            if team["leader_id"] == auth_user["id"]:
                return JSONResponse(status_code=400, content={"error": "你是队长本人，无需申请"})
            dup = safe_maybe_single(
                client.table("fs_team_members")
                .select("id, status")
                .eq("team_id", tid)
                .eq("user_id", auth_user["id"])
            )
            if dup and dup.get("status") in ("pending", "approved"):
                return JSONResponse(status_code=400, content={"error": "你已申请过或已是成员"})
            if dup:
                client.table("fs_team_members").update({"status": "pending", "note": note[:300]}).eq("id", dup["id"]).execute()
            else:
                client.table("fs_team_members").insert(
                    {"team_id": tid, "user_id": auth_user["id"], "role": "member", "status": "pending", "note": note[:300]}
                ).execute()
            # 给队长留言通知（复用信箱）
            me = safe_maybe_single(
                client.table("fs_users").select("nickname, grade, major, skill_tags, persona, profile_public").eq("id", auth_user["id"])
            ) or {}
            persona_txt = ""
            if me.get("profile_public") and me.get("persona"):
                p = me["persona"]
                p = p if isinstance(p, dict) else json.loads(p)
                persona_txt = "画像：" + "；".join(f"{k}：{v}" for k, v in p.items() if v and k in ("traits", "strengths"))[:100]
            msg = (
                f"【组队申请】{me.get('nickname', auth_user['nickname'])} 申请加入「{team['name']}」"
                f"（{me.get('grade') or ''} {me.get('major') or ''}，技能：{'、'.join((me.get('skill_tags') or [])[:5])}）。"
                f"{persona_txt} 申请说明：{note[:150] or '（无）'}。请在组队空间审批。"
            )
            client.table("fs_messages").insert(
                {"sender_id": auth_user["id"], "receiver_id": team["leader_id"], "content": msg[:500]}
            ).execute()
            return {"success": True, "message": "申请已提交，队长将在信箱中收到通知"}
        except Exception as e:  # noqa: BLE001
            logger.exception("[team_apply] failed")
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.post("/api/teams/{tid}/approve")
    async def api_team_approve(tid: int, request: Request):
        """队长通过申请 → 申请者信箱收到通过通知，团队进入协作空间"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            body = await request.json()
            user_id = int((body or {}).get("user_id"))
        except Exception:
            return JSONResponse(status_code=400, content={"error": "缺少 user_id"})
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            team = safe_maybe_single(client.table("fs_teams").select("id, name, leader_id").eq("id", tid))
            if not team or team["leader_id"] != auth_user["id"]:
                return JSONResponse(status_code=403, content={"error": "仅队长可审批"})
            resp = (
                client.table("fs_team_members")
                .update({"status": "approved"})
                .eq("team_id", tid)
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )
            if not rows_of(resp):
                return JSONResponse(status_code=404, content={"error": "无此待审申请"})
            client.table("fs_messages").insert(
                {
                    "sender_id": auth_user["id"],
                    "receiver_id": user_id,
                    "content": f"【组队通过】队长已通过你加入「{team['name']}」的申请！现在可以在组队空间进入团队协作空间与大家（和知颜）对话了。",
                }
            ).execute()
            # 全员到齐自动转 active（≥2 approved）
            approved = rows_of(
                client.table("fs_team_members")
                .select("id")
                .eq("team_id", tid)
                .eq("status", "approved")
                .execute()
            )
            if len(approved) >= 2:
                client.table("fs_teams").update({"status": "active"}).eq("id", tid).execute()
            return {"success": True}
        except Exception as e:  # noqa: BLE001
            logger.exception("[team_approve] failed")
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.post("/api/teams/{tid}/reject")
    async def api_team_reject(tid: int, request: Request):
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            body = await request.json()
            user_id = int((body or {}).get("user_id"))
        except Exception:
            return JSONResponse(status_code=400, content={"error": "缺少 user_id"})
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            team = safe_maybe_single(client.table("fs_teams").select("id, name, leader_id").eq("id", tid))
            if not team or team["leader_id"] != auth_user["id"]:
                return JSONResponse(status_code=403, content={"error": "仅队长可审批"})
            client.table("fs_team_members").delete().eq("team_id", tid).eq("user_id", user_id).eq("status", "pending").execute()
            client.table("fs_messages").insert(
                {
                    "sender_id": auth_user["id"],
                    "receiver_id": user_id,
                    "content": f"【组队通知】很抱歉，「{team['name']}」的队长暂未通过你的申请。别灰心，公开种子库里还有很多值得接力的方向。",
                }
            ).execute()
            return {"success": True}
        except Exception as e:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.put("/api/teams/{tid}/poster")
    async def api_team_update_poster(tid: int, request: Request):
        """v9.0 队长更新招募海报（base64 data URL，图片 ≤2.5MB）"""
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        body = await request.json()
        poster = str((body or {}).get("poster") or "").strip()
        if not poster.startswith("data:image/"):
            return JSONResponse(status_code=400, content={"error": "海报仅支持图片文件（png/jpg/webp/gif）"})
        try:
            import base64 as _b64

            b64 = poster.split(",", 1)[1] if "," in poster else ""
            if len(_b64.b64decode(b64, validate=False)) > 2_500_000:
                return JSONResponse(status_code=400, content={"error": "海报图片过大（≤2.5MB）"})
        except Exception:
            return JSONResponse(status_code=400, content={"error": "海报图片解析失败"})
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            team = safe_maybe_single(client.table("fs_teams").select("id, leader_id").eq("id", tid))
            if not team or team["leader_id"] != auth_user["id"]:
                return JSONResponse(status_code=403, content={"error": "仅队长可更换海报"})
            client.table("fs_teams").update({"poster_url": poster}).eq("id", tid).execute()
            return {"success": True}
        except Exception as e:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"error": str(e)})

    # ---------- 个人画像 ----------

    @app.get("/api/profile")
    async def api_profile_me(request: Request):
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            u = safe_maybe_single(
                client.table("fs_users")
                .select("nickname, grade, major, skill_tags, interest_tags, bio, persona, profile_public, contact")
                .eq("id", auth_user["id"])
            )
            persona = u.get("persona") if u else None
            if isinstance(persona, str):
                persona = json.loads(persona)
            return {"user": u, "persona": persona or {}, "profile_public": bool(u.get("profile_public"))}
        except Exception as e:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.put("/api/profile")
    async def api_profile_update(request: Request):
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid JSON"})
        persona = (body or {}).get("persona") or {}
        profile_public = (body or {}).get("profile_public")
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            patch = {"persona": json.dumps(persona, ensure_ascii=False)}
            if profile_public is not None:
                patch["profile_public"] = bool(profile_public)
            client.table("fs_users").update(patch).eq("id", auth_user["id"]).execute()
            return {"success": True}
        except Exception as e:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.get("/api/profile/{nickname}")
    async def api_profile_public(nickname: str):
        """查看他人画像（仅对方已公开时返回）"""
        try:
            from storage.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            u = safe_maybe_single(
                client.table("fs_users")
                .select("nickname, grade, major, skill_tags, interest_tags, bio, persona, profile_public")
                .eq("nickname", nickname)
            )
            if not u:
                return JSONResponse(status_code=404, content={"error": "用户不存在"})
            if not u.get("profile_public"):
                return JSONResponse(status_code=403, content={"error": "对方未公开画像"})
            persona = u.get("persona")
            if isinstance(persona, str):
                persona = json.loads(persona)
            return {
                "nickname": u["nickname"],
                "grade": u.get("grade"),
                "major": u.get("major"),
                "skill_tags": u.get("skill_tags") or [],
                "interest_tags": u.get("interest_tags") or [],
                "bio": u.get("bio"),
                "persona": persona or {},
            }
        except Exception as e:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.post("/api/chat")
    async def api_chat(request: Request):
        """SSE 流式对话接口。

        请求体: {"message": "用户输入文本", "session_id": "可选会话ID"}
        请求头: X-FS-Nickname / X-FS-Code（v7.0 登录态，必填）
        响应:   text/event-stream
                data: {"type":"delta","text":"增量文本"}
                data: {"type":"done"} / {"type":"error","message":"..."}
        """
        # v7.0 登录门槛：未登录不可对话
        try:
            auth_user = await asyncio.to_thread(_auth_user, request)
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"error": "登录态校验失败"})

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid JSON body"})

        message = (body or {}).get("message")
        if not isinstance(message, str) or not message.strip():
            return JSONResponse(status_code=400, content={"error": "field 'message' is required"})

        # v7.0 记忆持久化：会话线程绑定用户 id，跨设备/跨重启记忆不清零
        session_id = f"user-{auth_user['id']}-{auth_user['nickname']}"

        # v8.0 团队协作空间：team_id 切换到团队共享线程（全员共同记忆）
        team_ctx = None
        team_id = (body or {}).get("team_id")
        if team_id:
            try:
                from storage.database.supabase_client import get_supabase_client

                _tc = get_supabase_client()
                _team = safe_maybe_single(_tc.table("fs_teams").select("id, name, description, leader_id").eq("id", int(team_id)))
                if not _team:
                    return JSONResponse(status_code=404, content={"error": "团队不存在"})
                _m = safe_maybe_single(
                    _tc.table("fs_team_members")
                    .select("role, status")
                    .eq("team_id", int(team_id))
                    .eq("user_id", auth_user["id"])
                )
                if not ((_m and _m.get("status") == "approved") or _team["leader_id"] == auth_user["id"]):
                    return JSONResponse(status_code=403, content={"error": "你还不是该团队成员"})
                _members = rows_of(
                    _tc.table("fs_team_members")
                    .select("user_id, role")
                    .eq("team_id", int(team_id))
                    .eq("status", "approved")
                    .execute()
                )
                _uids = list({mm["user_id"] for mm in _members})
                _names = [uu["nickname"] for uu in rows_of(_tc.table("fs_users").select("nickname").in_("id", _uids).execute())] if _uids else []
                team_ctx = {
                    "id": _team["id"],
                    "name": _team["name"],
                    "desc": (_team.get("description") or "")[:120],
                    "members": _names,
                }
                session_id = f"team-{_team['id']}-chat"
            except PermissionError:
                raise
            except Exception as e:  # noqa: BLE001
                return JSONResponse(status_code=400, content={"error": f"团队校验失败：{e}"})

        # 懒加载 Agent (避免阻塞事件循环)
        try:
            graph = await asyncio.to_thread(_load_agent)
        except Exception as e:  # noqa: BLE001
            logger.exception("[web_chat] agent load failed")
            return JSONResponse(status_code=503, content={"error": f"agent load failed: {e}"})

        ctx = new_context(method="web_chat")
        ctx.run_id = session_id
        request_context.set(ctx)

        # v7.0 身份注入：知颜天然知道当前登录用户是谁（无需用户再报昵称）
        identity = f"[当前登录用户：{auth_user['nickname']}（{auth_user.get('grade') or ''} {auth_user.get('major') or ''}）] "
        if team_ctx:
            identity = (
                f"[团队协作空间「{team_ctx['name']}」｜成员：{'、'.join(team_ctx['members'])}｜"
                f"本期发言者：{auth_user['nickname']}（{auth_user.get('grade') or ''} {auth_user.get('major') or ''}）] "
            )
        # v8.0 首次对话：引导知颜自我介绍（名字由来+功能）并温柔询问个人信息
        first_chat_hint = ""
        if not team_ctx and not auth_user.get("intro_done"):
            first_chat_hint = (
                "[这是与该用户的第一次对话：请先温柔地自我介绍——名字「知颜」的由来"
                "（知晓你所说，也看见你所愿；四季轮回中陪你把每个念头种进土里）与你能做的事"
                "（灵感种子卡/项目建档/休眠唤醒/组队协作/留言牵线），然后体贴地询问对方年级、专业、"
                "擅长与兴趣，收集完成后调用 upsert_user_profile 建档并调用 upsert_profile 生成个人画像。] "
            )
        payload: Dict[str, Any] = {"messages": [{"role": "user", "content": first_chat_hint + identity + message}]}
        config = {"configurable": {"thread_id": f"web-{session_id}"}, "recursion_limit": 60}

        async def event_stream() -> AsyncGenerator[str, None]:
            # flow_state: 跟踪"工具调用后是否有文本产出"，覆盖两类空响应：
            # ① 整轮零文本（collected 为空） ② 工具执行完毕但模型沉默（GLM/豆包均偶发）
            flow_state = {"tool_seen": False, "text_after_tool": True}

            async def _stream(graph, cfg, payload_override=None) -> None:
                announced: set = set()
                async for chunk, _meta in graph.astream(
                    payload_override or payload, config=cfg, stream_mode="messages"
                ):
                    # ToolMessage (工具原始 JSON 结果) 不透传, 避免污染对话气泡
                    if not isinstance(chunk, AIMessageChunk):
                        continue

                    # 工具调用进度：模型的每条 AIMessage 各自从 index 0 开始编号，
                    # 所以用 (消息 id, index) 去重，避免第二个工具被误当成重复而漏报。
                    for tc in (getattr(chunk, "tool_call_chunks", None) or []):
                        name = tc.get("name")
                        key = (getattr(chunk, "id", None), tc.get("index"))
                        if name and key not in announced:
                            announced.add(key)
                            flow_state["tool_seen"] = True
                            flow_state["text_after_tool"] = False
                            yield _sse({
                                "type": "tool",
                                "label": _TOOL_LABELS.get(name, "正在处理…"),
                            })

                    content = chunk.content
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        text = "".join(
                            part.get("text", "") for part in content if isinstance(part, dict)
                        )
                    else:
                        continue
                    if not text:
                        continue
                    collected.append(text)
                    flow_state["text_after_tool"] = True
                    yield _sse({"type": "delta", "text": text})

            collected: list = []
            try:
                # checkpointer 故障（读 checkpoint 失败发生在任何输出之前）→ 降级无记忆图重跑
                try:
                    async for frame in _stream(graph, config):
                        yield frame
                except Exception as inner:  # noqa: BLE001
                    if not _is_conn_error(inner):
                        raise
                    logger.warning(
                        "[web_chat] session=%s checkpointer fault, degrade to no-memory: %s",
                        session_id, inner,
                    )
                    graph_nm = await asyncio.to_thread(_load_agent_no_memory)
                    cfg_nm = {
                        "configurable": {"thread_id": f"web-nomem-{session_id}"},
                        "recursion_limit": 60,
                    }
                    async for frame in _stream(graph_nm, cfg_nm):
                        yield frame
                # v6.2 兜底：模型空响应有两类形态（生产日志均出现过）——
                # ① 整轮零文本 ② 工具执行完毕但最终轮沉默（换 GLM 后更明显）。
                # 追加一次"基于工具结果作答"的提示重试，避免用户收到半截回复。
                need_nudge = (not collected) or (
                    flow_state["tool_seen"] and not flow_state["text_after_tool"]
                )
                if need_nudge:
                    logger.warning(
                        "[web_chat] session=%s empty/incomplete reply detected (collected=%d, tool_seen=%s), retrying with nudge",
                        session_id, sum(len(t) for t in collected),
                        flow_state["tool_seen"],
                    )
                    flow_state["tool_seen"] = False
                    flow_state["text_after_tool"] = True
                    yield _sse({"type": "delta", "text": ""})  # no-op，保持流活性
                    retry_payload = {
                        "messages": [
                            HumanMessage(
                                content="（系统提示：你刚才调用了工具但回复内容不完整。请基于对话中已有的工具结果与上下文，完整回答用户刚才的问题，不要重复调用工具。）"
                            )
                        ]
                    }
                    try:
                        async for frame in _stream(graph, config, payload_override=retry_payload):
                            yield frame
                    except Exception as retry_err:  # noqa: BLE001
                        logger.warning(
                            "[web_chat] session=%s retry failed: %s", session_id, retry_err
                        )
                logger.info(
                    "[web_chat] session=%s reply_chars=%d",
                    session_id,
                    sum(len(t) for t in collected),
                )
                # v10.0 团队空间：把本期对话写入共享聊天记录（全员互相可见）
                if team_ctx:
                    try:
                        from storage.database.supabase_client import get_supabase_client

                        def _persist_team_chat(client):
                            client.table("fs_team_chat_messages").insert([
                                {
                                    "team_id": int(team_ctx["id"]),
                                    "user_id": int(auth_user["id"]),
                                    "nickname": auth_user["nickname"],
                                    "role": "member",
                                    "content": message[:2000],
                                },
                                {
                                    "team_id": int(team_ctx["id"]),
                                    "user_id": None,
                                    "nickname": "知颜",
                                    "role": "assistant",
                                    "content": "".join(collected)[:4000],
                                },
                            ]).execute()

                        _c = get_supabase_client()
                        await asyncio.to_thread(_persist_team_chat, _c)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[web_chat] team chat persist failed: %s", e)
                # v8.0 首次对话完成：置 intro_done，后续对话不再自我介绍
                if first_chat_hint and not team_ctx:
                    try:
                        from storage.database.supabase_client import get_supabase_client

                        _c = get_supabase_client()
                        _c.table("fs_users").update({"intro_done": True}).eq("id", auth_user["id"]).execute()
                    except Exception:  # noqa: BLE001
                        logger.warning("[web_chat] mark intro_done failed uid=%s", auth_user["id"])
                yield _sse({"type": "done"})
            except asyncio.CancelledError:
                logger.info("[web_chat] session=%s cancelled by client", session_id)
                raise
            except Exception as e:  # noqa: BLE001
                logger.exception("[web_chat] session=%s failed", session_id)
                yield _sse({"type": "error", "message": f"对话执行异常：{e}"})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    logger.info("[web] Fifth-Season web routes registered: / /static /api/chat /api/health")


# ---------------------------------------------------------------------------
# 独立运行 (调试用): python src/web_server.py
# ---------------------------------------------------------------------------
_standalone_app = FastAPI(title="Fifth-Season Web (standalone)")
register_web(_standalone_app)


def parse_args():
    parser = argparse.ArgumentParser(description="第五季 Web Server (standalone)")
    parser.add_argument("-p", type=int, default=8000, help="HTTP port (default 8000, NEVER 9000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="bind host")
    return parser.parse_args()


if __name__ == "__main__":
    import uvicorn

    args = parse_args()
    if args.p == 9000:
        raise SystemExit("端口 9000 为平台系统服务保留，禁止占用。请使用其他端口（默认 8000）。")
    logger.info("Start Fifth-Season Web Server on %s:%s", args.host, args.p)
    uvicorn.run(_standalone_app, host=args.host, port=args.p, workers=1, reload=False)

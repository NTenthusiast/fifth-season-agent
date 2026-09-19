"""「第五季」工具层公共逻辑（普通函数，供多个 @tool 共用，禁止互相调用 @tool 对象）"""

import json
from datetime import datetime, timezone
from typing import Any, Optional, cast

from postgrest.exceptions import APIError

from storage.database.supabase_client import get_supabase_client


# ---------------------------------------------------------------------------
# Supabase 响应规整（规避 SDK JSON 联合类型的静态检查问题）
# ---------------------------------------------------------------------------
def rows_of(resp: Any) -> list:
    """把响应规整为行列表；空响应返回 []"""
    data = getattr(resp, "data", None)
    return list(data) if data else []


def as_row(resp: Any) -> dict:
    """取响应首行；无数据行时抛出异常（由调用方统一兜底）"""
    rows = rows_of(resp)
    if not rows:
        raise ValueError("数据库操作未返回数据行，请检查记录是否存在")
    return rows[0]


def maybe_row(resp: Any) -> Optional[dict]:
    """maybe_single 场景：单行或 None"""
    data = getattr(resp, "data", None)
    return data if isinstance(data, dict) else None


def safe_maybe_single(query: Any) -> Optional[dict]:
    """执行 maybe_single 查询；0 行时该网关 PostgREST 返回 406 PGRST116，
    此处将其规整为 None（语义即"记录不存在"），其余错误正常抛出。"""
    try:
        resp = query.maybe_single().execute()
        return maybe_row(resp)
    except APIError as e:
        code = getattr(e, "code", "") or ""
        msg = getattr(e, "message", "") or ""
        if code == "PGRST116" or "multiple (or no) rows" in msg or "0 rows" in msg:
            return None
        raise


# ---------------------------------------------------------------------------
# 四季状态机定义
# ---------------------------------------------------------------------------
STAGE_NAMES = {
    "spring": "春·萌芽",
    "summer": "夏·生长",
    "autumn": "秋·沉淀",
    "winter": "冬·蛰伏",
    "fifth": "第五季·重生",
}

# 合法流转表：key = (当前阶段, 目标阶段)
VALID_TRANSITIONS = {
    ("spring", "summer"): "项目进入执行阶段",
    ("summer", "autumn"): "项目阶段性沉淀总结",
    ("autumn", "summer"): "沉淀后继续推进",
    ("spring", "winter"): "项目休眠归档",
    ("summer", "winter"): "项目休眠归档",
    ("autumn", "winter"): "项目休眠归档",
    ("winter", "fifth"): "休眠项目被唤醒接棒",
    ("fifth", "summer"): "接棒后项目重启执行",
}


def stage_label(stage: str) -> str:
    return STAGE_NAMES.get(stage, stage)


def check_transition(current: str, target: str) -> tuple[bool, str]:
    """校验状态机流转是否合法，返回 (是否合法, 说明)"""
    if current == target:
        return False, f"项目已处于 {stage_label(current)} 阶段，无需流转"
    if (current, target) in VALID_TRANSITIONS:
        return True, VALID_TRANSITIONS[(current, target)]
    return (
        False,
        f"不允许从 {stage_label(current)} 流转到 {stage_label(target)}。"
        f"合法流转：spring→summer→autumn，任意活跃阶段→winter(休眠)，winter→fifth(唤醒)，fifth→summer(重启)",
    )


# ---------------------------------------------------------------------------
# 通用辅助
# ---------------------------------------------------------------------------
def result_str(payload: dict) -> str:
    """工具结果统一序列化为紧凑 JSON 字符串"""
    return json.dumps(payload, ensure_ascii=False, default=str)


def err_str(message: str) -> str:
    return result_str({"success": False, "error": message})


def parse_iso(value: str) -> Optional[datetime]:
    """解析 ISO8601 时间字符串（失败返回 None）"""
    if not value:
        return None
    try:
        v = value.strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _client():
    """获取 Supabase 客户端（service_role_key，服务端直连）"""
    return get_supabase_client()


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------
def find_user_by_nickname(nickname: str) -> Optional[dict]:
    """按昵称查用户档案，不存在返回 None"""
    nickname = (nickname or "").strip()
    if not nickname:
        return None
    try:
        return safe_maybe_single(
            _client()
            .table("fs_users")
            .select("id, nickname, grade, major, skill_tags, interest_tags, bio, created_at")
            .eq("nickname", nickname)
        )
    except APIError as e:
        raise Exception(f"查询用户失败: {e.message}")


def get_user_id(nickname: str) -> Optional[int]:
    user = find_user_by_nickname(nickname)
    return user["id"] if user else None


def require_user_id(nickname: str) -> int:
    """必须存在用户档案，否则抛出带引导信息的异常"""
    uid = get_user_id(nickname)
    if uid is None:
        raise ValueError(f"昵称「{nickname}」尚未建档，请先引导用户完成档案注册（upsert_user_profile）")
    return uid


def require_project_membership(project_id: int, nickname: str) -> int:
    """校验昵称是否为项目成员/负责人，是则返回其 user_id，否则抛出带引导信息的异常。

    用于阶段流转等只有项目成员才能执行的操作，防止误操作他人项目。
    """
    uid = require_user_id(nickname)
    project_id = int(project_id)
    try:
        row = safe_maybe_single(
            _client()
            .table("fs_project_members")
            .select("id")
            .eq("project_id", project_id)
            .eq("user_id", uid)
        )
    except APIError as e:
        raise Exception(f"校验成员失败: {e.message}")
    if row is None:
        raise ValueError(
            f"「{nickname}」不是项目 #{project_id} 的成员，无权执行此操作。"
            f"如需参与可先按申请-审批流程申请加入。"
        )
    return uid


# ---------------------------------------------------------------------------
# 项目
# ---------------------------------------------------------------------------
PROJECT_FIELDS = (
    "id, title, summary, domain_tags, required_skills, stage, "
    "founder_id, owner_id, hibernate_reason, hibernate_at, created_at, updated_at"
)


def find_project(project_id: int) -> Optional[dict]:
    try:
        return safe_maybe_single(
            _client()
            .table("fs_projects")
            .select(PROJECT_FIELDS)
            .eq("id", int(project_id))
        )
    except APIError as e:
        raise Exception(f"查询项目失败: {e.message}")
    except (TypeError, ValueError):
        raise Exception(f"项目 id 非法: {project_id}")


def require_project(project_id: int) -> dict:
    project = find_project(project_id)
    if project is None:
        raise ValueError(f"项目不存在（id={project_id}），请先通过 search_projects 检索确认")
    return project


def decorate_project(project: dict) -> dict:
    """给项目记录附加人类可读阶段名"""
    project = dict(project)
    project["stage_name"] = stage_label(project.get("stage", ""))
    return project


def fetch_user_names(user_ids: list) -> dict:
    """批量获取用户 id → 昵称映射（分批防 URL 超长）"""
    names: dict[int, str] = {}
    ids = [u for u in user_ids if u is not None]
    for i in range(0, len(ids), 50):
        batch = ids[i : i + 50]
        try:
            resp = (
                _client()
                .table("fs_users")
                .select("id, nickname")
                .in_("id", batch)
                .execute()
            )
            for row in rows_of(resp):
                names[row["id"]] = row["nickname"]
        except APIError as e:
            raise Exception(f"批量查询用户失败: {e.message}")
    return names


def latest_handover(project_id: int) -> Optional[dict]:
    """获取项目最新交接包"""
    try:
        resp = (
            _client()
            .table("fs_handover_packages")
            .select(
                "id, project_id, achievements, experience, pitfalls, "
                "remaining_issues, reusable_resources, created_at"
            )
            .eq("project_id", int(project_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = rows_of(resp)
        return rows[0] if rows else None
    except APIError as e:
        raise Exception(f"查询交接包失败: {e.message}")


def parse_json_list(raw: Any) -> list:
    """把交接包五段式字段（JSON 数组字符串）解析为 list，兼容已是 list 的情况"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else [str(data)]
    except (json.JSONDecodeError, TypeError):
        return [str(raw)]

"""「第五季·续种」传承扩展工具集：
传承故事墙 / 毕业季托付书 / 种子卡分享海报 / 项目健康巡检 /
全校技能图谱 / 需求投票唤醒 / 传承者成就体系 / 跨项目协作发现。

本文件同时提供 record_relay_story() 普通函数，供 awaken_project 在唤醒成功后
自动落一条「传承故事卡」（@tool 之间禁止互调，公共逻辑全部抽为普通函数）。
"""

import io
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from postgrest.exceptions import APIError

from langchain.tools import tool

from storage.database.supabase_client import get_supabase_client
from tools.db_helpers import (
    err_str,
    fetch_user_names,
    latest_handover,
    now_utc,
    parse_iso,
    require_project,
    require_project_membership,
    require_user_id,
    result_str,
    rows_of,
)

logger = logging.getLogger("fifth_season.legacy")

# ---------------------------------------------------------------------------
# 传承故事卡（供 awaken_project 调用的普通函数）
# ---------------------------------------------------------------------------
def _story_text(project: dict, founder: str, successor: str, period_days: int) -> str:
    if period_days >= 1:
        wait = f"在校园记忆库中沉睡了 {period_days} 天"
    else:
        wait = "刚在记忆库中落定"
    return (
        f"「{project['title']}」由 {founder} 发起，{wait}，"
        f"被 {successor} 唤醒接棒——第五季，让未完成的美好重新发生。"
    )


def record_relay_story(
    project: dict,
    successor_nickname: str,
    match_reason: str,
    awaken_record_id: Optional[int] = None,
) -> None:
    """唤醒成功后写入传承故事卡（best-effort：失败仅记日志，不影响唤醒主流程）"""
    try:
        client = get_supabase_client()
        names = fetch_user_names(
            [project.get("founder_id"), project.get("owner_id")]
        )
        founder = names.get(project.get("founder_id"), "往届同学")
        hibernate_at = parse_iso(project.get("hibernate_at") or "")
        created_at = parse_iso(project.get("created_at") or "")
        base = hibernate_at or created_at
        period_days = 0
        if base:
            period_days = max(0, (now_utc() - base).days)
        handover = latest_handover(project["id"])
        highlights: list = []
        if handover:
            raw = handover.get("achievements")
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                    highlights = parsed if isinstance(parsed, list) else [raw]
                except (json.JSONDecodeError, TypeError):
                    highlights = [raw] if raw else []
            elif isinstance(raw, list):
                highlights = raw
        client.table("fs_stories").insert(
            {
                "awaken_record_id": awaken_record_id,
                "project_id": project["id"],
                "project_title": project["title"],
                "founder_nickname": founder,
                "successor_nickname": successor_nickname,
                "match_reason": match_reason,
                "story_text": _story_text(project, founder, successor_nickname, period_days),
                "highlights": highlights[:5],
                "period_days": period_days,
                "is_featured": True,
            }
        ).execute()
    except Exception as e:  # noqa: BLE001
        logger.warning("[story] record relay story failed: %s", e)


# ---------------------------------------------------------------------------
# 传承故事墙
# ---------------------------------------------------------------------------
@tool
def get_relay_stories(limit: int = 8, featured_only: bool = False) -> str:
    """获取「传承故事墙」故事卡列表：每一次休眠项目被唤醒接棒，都会生成一张故事卡
    （原负责人 → 接棒者 → 匹配理由 → 前人留下的高光成果）。
    典型用途：用户想看真实发生的传承故事、路演/展示需要传承案例时调用。
    不适用：查看某个具体项目的完整资料请用 get_project_detail；
    查看全校哪些项目需要关注请用 get_project_health。

    Args:
        limit: 最多返回条数，默认8
        featured_only: 是否只看精选故事，默认False
    """
    try:
        client = get_supabase_client()
        query = (
            client.table("fs_stories")
            .select(
                "id, project_id, project_title, founder_nickname, successor_nickname, "
                "match_reason, story_text, highlights, period_days, is_featured, likes, created_at"
            )
            .order("created_at", desc=True)
            .limit(max(1, min(int(limit), 30)))
        )
        if featured_only:
            query = query.eq("is_featured", True)
        rows = rows_of(query.execute())
        if not rows:
            return result_str(
                {"success": True, "stories": [], "message": "故事墙还空着——下一次唤醒接棒，将写下第一张传承故事卡。"}
            )
        return result_str(
            {
                "success": True,
                "count": len(rows),
                "stories": rows,
                "message": "以上为真实发生的传承故事（数据来自唤醒记录），请用有温度但不夸张的方式转述。",
            }
        )
    except APIError as e:
        return err_str(f"查询故事墙失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


# ---------------------------------------------------------------------------
# 成就体系（普通函数 + 工具）
# ---------------------------------------------------------------------------
# 成就规则：code -> (所需统计键, 阈值)。统计键：founded/handovers/awakenings/votes
AWARD_RULES = [
    ("first_seed", "founded", 1),
    ("seed_farmer_3", "founded", 3),
    ("handover_master", "handovers", 1),
    ("first_awaken", "awakenings", 1),
    ("relay_guardian", "awakenings", 2),
    ("community_voice", "votes", 1),
    ("vote_star", "votes", 5),
]

_NEXT_AWARD_HINT = {
    "first_seed": "创建 1 个项目种子卡",
    "seed_farmer_3": "累计发起 3 个项目",
    "handover_master": "为项目沉淀 1 份交接包",
    "first_awaken": "唤醒接棒 1 个休眠项目",
    "relay_guardian": "累计唤醒 2 个项目",
    "community_voice": "为休眠项目投 1 票",
    "vote_star": "累计投票 5 次",
}


def compute_user_stats(user_id: int, nickname: str) -> dict:
    """从真实活动数据统计用户的传承行为（成就判定的唯一数据源）"""
    client = get_supabase_client()
    founded = rows_of(
        client.table("fs_projects").select("id").eq("founder_id", user_id).execute()
    )
    my_project_ids = [r["id"] for r in founded] or [-1]
    handovers = rows_of(
        client.table("fs_handover_packages")
        .select("id", "project_id")
        .in_("project_id", my_project_ids)
        .execute()
    )
    awakenings = rows_of(
        client.table("fs_awaken_records").select("id").eq("successor_id", user_id).execute()
    )
    votes = rows_of(
        client.table("fs_votes").select("id").eq("voter_nickname", nickname).execute()
    )
    return {
        "founded": len(founded),
        "handovers": len(handovers),
        "awakenings": len(awakenings),
        "votes": len(votes),
    }


def _earned_codes(stats: dict) -> list[str]:
    earned = []
    for code, key, threshold in AWARD_RULES:
        if stats.get(key, 0) >= threshold:
            earned.append(code)
    return earned


def sync_user_awards(user_id: int, nickname: str) -> tuple[list[dict], int]:
    """按真实活动数据补发用户尚未持有的成就，返回(已持有成就列表, 总贡献值)"""
    client = get_supabase_client()
    stats = compute_user_stats(user_id, nickname)
    earned = _earned_codes(stats)
    award_rows = rows_of(
        client.table("fs_awards").select("id, code, name, description, icon, category, points").execute()
    )
    by_code = {r["code"]: r for r in award_rows}
    held = rows_of(
        client.table("fs_user_awards").select("award_id, awarded_at, reason")
        .eq("user_id", user_id).execute()
    )
    held_ids = {r["award_id"] for r in held}
    for code in earned:
        award = by_code.get(code)
        if not award or award["id"] in held_ids:
            continue
        client.table("fs_user_awards").insert(
            {"user_id": user_id, "award_id": award["id"], "reason": _NEXT_AWARD_HINT.get(code, "")}
        ).execute()
    # 重新拉取合并后的持有列表
    merged = rows_of(
        client.table("fs_user_awards")
        .select("awarded_at, reason, fs_awards(code, name, description, icon, category, points)")
        .eq("user_id", user_id).execute()
    )
    awards = []
    total = 0
    for row in merged:
        info = row.get("fs_awards") or {}
        total += int(info.get("points") or 0)
        awards.append(
            {
                "code": info.get("code"),
                "name": info.get("name"),
                "icon": info.get("icon"),
                "description": info.get("description"),
                "points": info.get("points"),
                "awarded_at": row.get("awarded_at"),
            }
        )
    return awards, total


def compute_all_user_points() -> list[dict]:
    """全校用户贡献值排行（基于真实活动数据实时计算，不依赖懒同步）。

    v9.0 积分标准（严格规定，与风云榜规则说明保持一致）：
      · 档案建立          +5   （fs_users 建档即得）
      · 唤醒接棒          +30  （每次 fs_awaken_records 记录，接棒一个休眠项目）
      · 双料传承人        +50  （累计接棒 ≥ 2 次，额外一次性加成）
      · 发起种子项目      +10  （fs_projects 中任 founder，每个 +10）
      · 多产发起人        +30  （累计发起 ≥ 3 个项目，额外一次性加成）
      · 沉淀交接包        +15  （名下项目交出完整交接包，每个 +15）
      · 项目完成传承      +40  （项目达到 fifth「已完成·传承中」阶段）
      · 为种子投票        +5   （首次投票起，每票 +5）
      · 投票召集人        +20  （累计投票 ≥ 5 票，额外一次性加成）
      · 存个人种子卡      +5   （每张灵感种子卡）
      · 引入公开种子卡    +15  （把项目引入自己的种子库，每个 +15）
      · 团队组建成功      +20  （名下团队从招募转为协作状态，每支 +20）
      · 留言牵线          +2   （通过信箱给他人留言，每条 +2，上限 20）
    """
    client = get_supabase_client()
    users = rows_of(client.table("fs_users").select("id, nickname, grade, major, profile_public").execute())
    projects = rows_of(client.table("fs_projects").select("id, founder_id, stage").execute())
    handovers = rows_of(client.table("fs_handover_packages").select("project_id").execute())
    awakenings = rows_of(client.table("fs_awaken_records").select("successor_id, project_id").execute())
    votes = rows_of(client.table("fs_votes").select("voter_nickname").execute())
    inspirations = rows_of(client.table("fs_inspirations").select("user_id").execute())
    imports = rows_of(client.table("fs_project_members").select("user_id").execute())
    teams = rows_of(client.table("fs_teams").select("leader_id, status").execute())
    messages = rows_of(client.table("fs_messages").select("sender_id").execute())
    points_map = {
        u["id"]: {
            "nickname": u["nickname"],
            "grade": u.get("grade"),
            "major": u.get("major"),
            "profile_public": bool(u.get("profile_public")),
            "points": 0,
            "tags": [],
        }
        for u in users
    }
    # 档案建立 +5
    for uid in points_map:
        points_map[uid]["points"] += 5
    # 发起种子项目 +10/个；项目完成传承 +40/个；沉淀交接包 +15/个（交包的发起人）
    handover_project_ids = {h["project_id"] for h in handovers}
    founded_count: dict[int, int] = {}
    done_count: dict[int, int] = {}
    handover_cnt: dict[int, int] = {}
    for p in projects:
        fid = p.get("founder_id")
        if fid and fid in points_map:
            founded_count[fid] = founded_count.get(fid, 0) + 1
            points_map[fid]["points"] += 10
            if p.get("stage") == "fifth":
                points_map[fid]["points"] += 40
                done_count[fid] = done_count.get(fid, 0) + 1
        if p["id"] in handover_project_ids and fid and fid in points_map:
            points_map[fid]["points"] += 15  # handover_master
            handover_cnt[fid] = handover_cnt.get(fid, 0) + 1
    for uid, cnt in founded_count.items():
        if uid in points_map:
            if cnt >= 3:
                points_map[uid]["points"] += 30
                points_map[uid]["tags"].append("多产发起人")
            if cnt:
                points_map[uid]["tags"].append("发起×%d" % cnt)
    for uid, cnt in done_count.items():
        if uid in points_map and cnt:
            points_map[uid]["tags"].append("完成传承×%d" % cnt)
    for uid, cnt in handover_cnt.items():
        if uid in points_map and cnt:
            points_map[uid]["tags"].append("交接包×%d" % cnt)
    # 唤醒接棒 +30/次
    awaken_count: dict[int, int] = {}
    for a in awakenings:
        sid = a.get("successor_id")
        if sid in points_map:
            points_map[sid]["points"] += 30
        if sid:
            awaken_count[sid] = awaken_count.get(sid, 0) + 1
    # 双料传承人 +50（接棒 ≥ 2 次）
    for uid, cnt in awaken_count.items():
        if uid in points_map and cnt:
            points_map[uid]["tags"].append("接棒×%d" % cnt)
            if cnt >= 2:
                points_map[uid]["points"] += 50
                points_map[uid]["tags"].append("双料传承人")
    # 为种子投票 +5/票；投票召集人 +20（≥5 票）
    vote_count: dict[str, int] = {}
    for v in votes:
        nick = v.get("voter_nickname")
        if nick:
            vote_count[nick] = vote_count.get(nick, 0) + 1
    by_nick = {u["nickname"]: u["id"] for u in users}
    for nick, cnt in vote_count.items():
        uid = by_nick.get(nick)
        if uid and uid in points_map:
            points_map[uid]["points"] += 5 * cnt
            if cnt:
                points_map[uid]["tags"].append("投票×%d" % cnt)
            if cnt >= 5:
                points_map[uid]["points"] += 20
                points_map[uid]["tags"].append("召集人")
    # 存个人种子卡 +5/张
    seedcard_cnt: dict[int, int] = {}
    for ins in inspirations:
        uid = ins.get("user_id")
        if uid in points_map:
            points_map[uid]["points"] += 5
            seedcard_cnt[uid] = seedcard_cnt.get(uid, 0) + 1
    for uid, cnt in seedcard_cnt.items():
        if uid in points_map and cnt:
            points_map[uid]["tags"].append("种子卡×%d" % cnt)
    # 引入公开种子卡 +15/个
    import_cnt: dict[int, int] = {}
    for imp in imports:
        uid = imp.get("user_id")
        if uid in points_map:
            points_map[uid]["points"] += 15
            import_cnt[uid] = import_cnt.get(uid, 0) + 1
    for uid, cnt in import_cnt.items():
        if uid in points_map and cnt:
            points_map[uid]["tags"].append("引入×%d" % cnt)
    # 团队组建成功 +20/支（队长，团队进入 active 协作状态）
    team_cnt: dict[int, int] = {}
    for t in teams:
        lid = t.get("leader_id")
        if lid in points_map and t.get("status") == "active":
            points_map[lid]["points"] += 20
            team_cnt[lid] = team_cnt.get(lid, 0) + 1
    for uid, cnt in team_cnt.items():
        if uid in points_map and cnt:
            points_map[uid]["tags"].append("带队×%d" % cnt)
    # 留言牵线 +2/条（封顶 20 分）
    msg_count: dict[int, int] = {}
    for m in messages:
        sid = m.get("sender_id")
        if sid:
            msg_count[sid] = msg_count.get(sid, 0) + 1
    for uid, cnt in msg_count.items():
        if uid in points_map:
            points_map[uid]["points"] += min(cnt, 10) * 2
            if cnt:
                points_map[uid]["tags"].append("留言×%d" % min(cnt, 10))
    ranked = sorted(points_map.items(), key=lambda kv: (kv[1]["points"], -kv[0]), reverse=True)
    out = []
    for _uid, info in ranked:
        # 贡献值为 0 的用户不上榜；排名在过滤之后重排，避免出现 1、2、5、7 这样的跳号
        if info["points"] <= 0:
            continue
        out.append({
            "rank": len(out) + 1,
            "user_id": _uid,
            "nickname": info["nickname"],
            "grade": info["grade"],
            "major": info["major"],
            "profile_public": info["profile_public"],
            "points": info["points"],
            "breakdown": " · ".join(info["tags"]),
        })
    return out


POINT_RULES: list[dict] = [
    {"label": "档案建立", "points": "+5", "desc": "在知颜处完成注册建档（昵称/年级/专业）"},
    {"label": "唤醒接棒", "points": "+30", "desc": "每接棒一个休眠项目（生成唤醒记录）"},
    {"label": "双料传承人", "points": "+50", "desc": "累计接棒 ≥ 2 个项目，一次性加成"},
    {"label": "发起种子项目", "points": "+10", "desc": "每发起一个项目种子"},
    {"label": "多产发起人", "points": "+30", "desc": "累计发起 ≥ 3 个项目，一次性加成"},
    {"label": "沉淀交接包", "points": "+15", "desc": "名下项目每交出一份完整交接包"},
    {"label": "项目完成传承", "points": "+40", "desc": "项目进入「已完成·传承中」阶段"},
    {"label": "为种子投票", "points": "+5", "desc": "每次为休眠项目投出「我也想用」"},
    {"label": "投票召集人", "points": "+20", "desc": "累计投票 ≥ 5 次，一次性加成"},
    {"label": "存个人种子卡", "points": "+5", "desc": "每存一张个人灵感种子卡"},
    {"label": "引入公开种子卡", "points": "+15", "desc": "把项目引入自己的种子库，每个 +15"},
    {"label": "团队组建成功", "points": "+20", "desc": "队长组建的团队进入协作状态，每支"},
    {"label": "留言牵线", "points": "+2", "desc": "通过信箱给他人留言，每条（封顶 20 分）"},
]


@tool
def get_my_awards(nickname: str) -> str:
    """查询用户的「传承者成就」：已解锁的勋章、贡献值、全校排行与下一枚勋章的解锁提示。
    成就完全由真实行为判定（发起项目/沉淀交接包/唤醒接棒/为种子投票），禁止单独发放。

    Args:
        nickname: 用户昵称（必须已建档）
    """
    try:
        user_id = require_user_id(nickname)
        awards, total = sync_user_awards(user_id, nickname)
        leaderboard = compute_all_user_points()
        rank = next((r["rank"] for r in leaderboard if r["user_id"] == user_id), None)
        stats = compute_user_stats(user_id, nickname)
        earned = set(_earned_codes(stats))
        next_hints = [
            {"award": by[0], "hint": _NEXT_AWARD_HINT.get(by[0], "")}
            for by in AWARD_RULES
            if by[0] not in earned
        ][:3]
        return result_str(
            {
                "success": True,
                "nickname": nickname,
                "awards": awards,
                "total_points": total,
                "rank": rank or "暂未上榜",
                "activity_stats": stats,
                "next_hints": next_hints,
                "top3": leaderboard[:3],
                "message": "成就与贡献值全部来自真实传承行为，请如实呈现，不夸大。",
            }
        )
    except ValueError as e:
        return err_str(str(e))
    except APIError as e:
        return err_str(f"查询成就失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


# ---------------------------------------------------------------------------
# 需求投票（需先建档，防刷票）
# ---------------------------------------------------------------------------
@tool
def vote_awaken_request(nickname: str, project_id: int) -> str:
    """为休眠种子投出「我也想用」的一票（需求投票唤醒机制）。
    投票需先建档（防刷票）；票数高的休眠项目会被优先推荐唤醒。
    典型用途：用户表达「希望某个休眠项目被做下去」时调用。

    Args:
        nickname: 投票人昵称（必须已建档，未建档先引导 upsert_user_profile）
        project_id: 休眠项目id
    """
    try:
        user_id = require_user_id(nickname)
        project = require_project(project_id)
        if project["stage"] != "winter":
            return err_str(
                f"项目「{project['title']}」当前处于{project['stage']}阶段，只有冬·蛰伏(休眠)中的种子可以投票唤醒"
            )
        client = get_supabase_client()
        try:
            client.table("fs_votes").insert(
                {"project_id": int(project_id), "voter_nickname": nickname}
            ).execute()
            action = "投票成功"
        except APIError as e:
            if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
                action = "已投过票（每人每项目一票）"
            else:
                raise
        votes = rows_of(
            client.table("fs_votes").select("id").eq("project_id", int(project_id)).execute()
        )
        # 顺手记录一条项目动态（投票是公共可见的需求信号）
        client.table("fs_project_updates").insert(
            {
                "project_id": int(project_id),
                "author_id": user_id,
                "content": f"「{nickname}」投出唤醒需求票：我也想用这个项目（当前 {len(votes)} 票）",
                "stage": "winter",
            }
        ).execute()
        # 投票排行（供优先唤醒排序）
        top = rows_of(
            client.table("fs_votes").select("project_id, voter_nickname").execute()
        )
        counts: dict[int, int] = {}
        for row in top:
            counts[row["project_id"]] = counts.get(row["project_id"], 0) + 1
        return result_str(
            {
                "success": True,
                "action": action,
                "project_title": project["title"],
                "votes": len(votes),
                "vote_ranking": sorted(
                    [{"project_id": k, "votes": v} for k, v in counts.items()],
                    key=lambda x: x["votes"],
                    reverse=True,
                )[:5],
                "message": "票数是唤醒优先级的重要信号；请鼓励用户邀请更多同学为想要的项目投票。",
            }
        )
    except ValueError as e:
        return err_str(str(e))
    except APIError as e:
        return err_str(f"投票失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


# ---------------------------------------------------------------------------
# 全校技能图谱
# ---------------------------------------------------------------------------
def _count_tags(rows: list, field: str) -> dict[str, int]:
    counter: dict[str, int] = {}
    for row in rows:
        tags = row.get(field) or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = [tags]
        for tag in tags:
            if tag and str(tag).strip():
                key = str(tag).strip()
                counter[key] = counter.get(key, 0) + 1
    return counter


@tool
def get_skill_graph(top_n: int = 10) -> str:
    """获取「全校技能图谱」：校园能力供给（同学拥有的技能）与需求（项目需要的能力）对比。
    典型用途：分析哪些能力稀缺（需求>供给，值得招募培养）、哪些富余（供给>需求，适合发起项目）。

    Args:
        top_n: 返回前N个技能，默认10
    """
    try:
        client = get_supabase_client()
        users = rows_of(client.table("fs_users").select("skill_tags").execute())
        projects = rows_of(client.table("fs_projects").select("required_skills").execute())
        supply = _count_tags(users, "skill_tags")
        demand = _count_tags(projects, "required_skills")
        skills = set(supply) | set(demand)
        items = []
        for s in skills:
            sup, dem = supply.get(s, 0), demand.get(s, 0)
            items.append(
                {
                    "skill": s,
                    "supply": sup,
                    "demand": dem,
                    "gap": dem - sup,
                    "status": "稀缺" if dem - sup > 0 else ("均衡" if sup == dem and dem > 0 else "富余"),
                }
            )
        items.sort(key=lambda x: (x["gap"], x["demand"]), reverse=True)
        top = items[: max(1, min(int(top_n), 30))]
        return result_str(
            {
                "success": True,
                "top": top,
                "summary": {
                    "users": len(users),
                    "projects": len(projects),
                    "scarcest": top[0]["skill"] if top else None,
                },
                "message": "稀缺能力=需求>供给（建议招募或培养）；富余能力=供给>需求（适合发起项目）。请基于真实数字给建议。",
            }
        )
    except APIError as e:
        return err_str(f"统计技能图谱失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


# ---------------------------------------------------------------------------
# 项目健康度巡检
# ---------------------------------------------------------------------------
@tool
def get_project_health(scope: str = "all") -> str:
    """项目健康度巡检（AI 主动守护）：检查休眠超期、生长停滞、待托付沉淀的项目。
    典型用途：用户询问「最近有什么需要关注的」「帮我巡检一下项目」或管理员想全局查看时调用。
    不适用：查看某个项目的详细资料请用 get_project_detail；检索项目请用 search_projects。

    Args:
        scope: all=全部 / dormant=休眠种子 / stalled=停滞项目 / handover=待托付项目，默认all
    """
    try:
        client = get_supabase_client()
        projects = rows_of(
            client.table("fs_projects")
            .select(
                "id, title, stage, founder_id, owner_id, hibernate_at, "
                "hibernate_reason, updated_at, created_at"
            )
            .execute()
        )
        updates = rows_of(
            client.table("fs_project_updates").select("project_id, created_at").order("created_at", desc=True).limit(500).execute()
        )
        latest_update: dict[int, str] = {}
        for u in updates:
            pid = u.get("project_id")
            if pid not in latest_update:
                latest_update[pid] = u.get("created_at") or ""
        votes = rows_of(client.table("fs_votes").select("project_id").execute())
        vote_counts: dict[int, int] = {}
        for v in votes:
            vote_counts[v["project_id"]] = vote_counts.get(v["project_id"], 0) + 1
        now = now_utc()
        dormant, stalled, handover = [], [], []
        for p in projects:
            stage = p.get("stage")
            updated = parse_iso(p.get("updated_at") or p.get("created_at") or "")
            days_idle = max(0, (now - updated).days) if updated else None
            if stage == "winter":
                hib = parse_iso(p.get("hibernate_at") or p.get("created_at") or "")
                days = max(0, (now - hib).days) if hib else 0
                dormant.append(
                    {
                        "project_id": p["id"],
                        "title": p["title"],
                        "dormant_days": days,
                        "votes": vote_counts.get(p["id"], 0),
                        "reason": p.get("hibernate_reason") or "未记录",
                    }
                )
            elif stage in ("spring", "summer"):
                if days_idle is not None and days_idle >= 21:
                    stalled.append(
                        {
                            "project_id": p["id"],
                            "title": p["title"],
                            "stage": stage,
                            "days_without_update": days_idle,
                        }
                    )
            elif stage == "autumn":
                handover.append(
                    {
                        "project_id": p["id"],
                        "title": p["title"],
                        "suggestion": "已完成沉淀，建议生成交接包并托付/休眠，或直接推进第五季唤醒",
                    }
                )
        dormant.sort(key=lambda x: (x["votes"], x["dormant_days"]), reverse=True)
        payload: dict[str, Any] = {"success": True}
        if scope in ("all", "dormant"):
            payload["dormant_seeds"] = dormant[:10]
        if scope in ("all", "stalled"):
            payload["stalled_projects"] = stalled[:10]
        if scope in ("all", "handover"):
            payload["handover_ready"] = handover[:10]
        payload["message"] = (
            "巡检结果：休眠种子按(票数,休眠天数)排序即为唤醒优先级；停滞项目建议主动询问近况；"
            "待托付项目建议引导负责人生成交接包。请给出具体可执行的下一步建议。"
        )
        return result_str(payload)
    except APIError as e:
        return err_str(f"巡检失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


# ---------------------------------------------------------------------------
# 跨项目协作发现
# ---------------------------------------------------------------------------
@tool
def discover_project_synergy(project_id: Optional[int] = None) -> str:
    """跨项目协作发现：识别领域相近、能力互补、可以联手的项目对，AI 主动牵线。
    典型用途：用户问「我的项目还能和谁合作」「校园里有没有类似项目」时调用。
    不适用：找合作的人请用 find_users_by_tags；看全校能力供需请用 get_skill_graph。

    Args:
        project_id: 聚焦某个项目id寻找它的协作对象（可选；不传则给出全校最值得联手的组合）
    """
    try:
        client = get_supabase_client()
        projects = rows_of(
            client.table("fs_projects")
            .select("id, title, domain_tags, required_skills, stage, owner_id")
            .execute()
        )
        by_id = {p["id"]: p for p in projects}

        def _tags(p: dict, field: str) -> set:
            raw = p.get(field) or []
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    raw = [raw]
            return {str(t).strip() for t in raw if t and str(t).strip()}

        pairs = []
        for i, a in enumerate(projects):
            for b in projects[i + 1:]:
                dom_a, dom_b = _tags(a, "domain_tags"), _tags(b, "domain_tags")
                shared_dom = dom_a & dom_b
                if not shared_dom:
                    continue
                skill_a, skill_b = _tags(a, "required_skills"), _tags(b, "required_skills")
                overlap = len(skill_a & skill_b)
                # 能力互补：技能重叠不多但领域同频（避免同质化竞争）
                if overlap >= min(len(skill_a), len(skill_b)) and skill_a and skill_b and overlap == len(skill_a):
                    continue
                pairs.append(
                    {
                        "pair": [a["title"], b["title"]],
                        "ids": [a["id"], b["id"]],
                        "shared_domains": sorted(shared_dom)[:3],
                        "stages": [a.get("stage"), b.get("stage")],
                        "synergy_hint": f"同属「{('/'.join(sorted(shared_dom)[:2]))}」领域，能力侧重不同，可考虑联合推进或共享资源",
                    }
                )
        if project_id is not None:
            project = by_id.get(int(project_id))
            if not project:
                return err_str(f"项目不存在（id={project_id}）")
            focused = [p for p in pairs if int(project_id) in p["ids"]][:5]
            return result_str(
                {
                    "success": True,
                    "project": project["title"],
                    "synergies": focused,
                    "message": "围绕该项目给出协作建议；若列表为空，说明暂无领域相近的其他项目。",
                }
            )
        pairs = pairs[:6]
        return result_str(
            {
                "success": True,
                "synergies": pairs,
                "message": "以上为领域同频、能力互补的项目组合，请自然地给出联手建议，不强行撮合。",
            }
        )
    except APIError as e:
        return err_str(f"协作发现失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


# ---------------------------------------------------------------------------
# 托付书 / 种子卡海报（Pillow 渲染管线）
# ---------------------------------------------------------------------------
_FONT_PATHS = (
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)

# 站点配色（与前端一致的现代简约暖纸风）
_C_PAPER = (250, 247, 240)
_C_INK = (61, 58, 52)
_C_MUTED = (138, 133, 120)
_C_GREEN = (126, 169, 139)
_C_GREEN_LIGHT = (239, 245, 239)
_C_GOLD = (232, 182, 76)
_C_LINE = (214, 208, 194)

STAGE_BADGE = {
    "spring": "🌱 春 · 萌芽",
    "summer": "☀️ 夏 · 生长",
    "autumn": "🍂 秋 · 沉淀",
    "winter": "❄️ 冬 · 蛰伏",
    "fifth": "✨ 第五季 · 重生",
}


def _font(size: int):
    from PIL import ImageFont

    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    """按像素宽度换行（CJK 逐字累积，ASCII 词尽量不拆）"""
    lines: list[str] = []
    for para in str(text or "").split("\n"):
        line = ""
        for ch in para:
            if font.getlength(line + ch) > max_width and line:
                lines.append(line)
                line = ch
            else:
                line += ch
        lines.append(line)
    return lines


def _center(draw, xy_top: tuple, text: str, font, fill) -> float:
    x, y = xy_top
    w = font.getlength(text)
    draw.text((x - w / 2, y), text, font=font, fill=fill)
    return y + font.size


def _upload_image(png_bytes: bytes, base_name: str) -> dict:
    """上传生成图：优先平台对象存储（24h 签名链接）；
    自部署（无桶配置）时落到本地 assets/web/uploads，经 /static 直链访问。"""
    import os

    file_name = f"{base_name}_{int(time.time())}.png"

    bucket_name = os.getenv("COZE_BUCKET_NAME")
    endpoint_url = os.getenv("COZE_BUCKET_ENDPOINT_URL")
    if not bucket_name or not endpoint_url:
        # 自部署兜底：assets/web 已由 web_server 挂载在 /static
        uploads_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "assets", "web", "uploads",
        )
        os.makedirs(uploads_dir, exist_ok=True)
        with open(os.path.join(uploads_dir, file_name), "wb") as f:
            f.write(png_bytes)
        return {"file_key": file_name, "url": f"/static/uploads/{file_name}"}

    from coze_coding_dev_sdk.s3 import S3SyncStorage

    storage = S3SyncStorage(
        endpoint_url=endpoint_url,
        access_key="",
        secret_key="",
        bucket_name=bucket_name,
        region="cn-beijing",
    )
    key = storage.upload_file(file_content=png_bytes, file_name=file_name, content_type="image/png")
    url = storage.generate_presigned_url(key=key, expire_time=86400)
    return {"file_key": key, "url": url}


def _parse_list_field(raw: Any) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else [str(raw)]
    except (json.JSONDecodeError, TypeError):
        return [str(raw)]


def _render_certificate(project: dict, founder: str, owner: str,
                        achievements: list, message: str, stage: str) -> bytes:
    """毕业季·项目托付书（现代简约暖纸风 1080×1440）"""
    from PIL import Image, ImageDraw

    W, H = 1080, 1440
    img = Image.new("RGB", (W, H), _C_PAPER)
    d = ImageDraw.Draw(img)
    f_badge, f_title, f_sub = _font(30), _font(84), _font(30)
    f_proj, f_label, f_value, f_small = _font(52), _font(28), _font(32), _font(24)
    f_quote, f_foot = _font(32), _font(24)

    # 双层边框
    d.rounded_rectangle([44, 44, W - 44, H - 44], radius=30, outline=_C_GREEN, width=3)
    d.rounded_rectangle([62, 62, W - 62, H - 62], radius=22, outline=(*_C_GOLD, 90), width=1)

    y = 128
    y = _center(d, (W / 2, y), "第五季 · 续种 ｜ FIFTH SEASON", f_badge, _C_GREEN) + 18
    y = _center(d, (W / 2, y), "❋", f_sub, _C_GOLD) + 22
    y = _center(d, (W / 2, y), "项目托付书", f_title, _C_INK) + 14
    _center(d, (W / 2, y), "毕业季 · 把热爱托付给下一双手", f_sub, _C_MUTED)

    # 项目卡
    y = 424
    d.rounded_rectangle([104, y, W - 104, y + 208], radius=18, fill=_C_GREEN_LIGHT)
    lines = _wrap_text(project.get("title") or "未命名项目", f_proj, W - 260)[:2]
    ty = y + 40
    for line in lines:
        d.text((W / 2 - f_proj.getlength(line) / 2, ty), line, font=f_proj, fill=_C_INK)
        ty += 66
    badge = f"种子卡 #{project['id']} · {STAGE_BADGE.get(stage, stage)}"
    d.text((W / 2 - f_small.getlength(badge) / 2, y + 168), badge, font=f_small, fill=_C_GREEN)

    # 信息行
    y += 250
    info = [
        ("发起人", founder),
        ("现任负责人", owner),
        ("领域", " / ".join((project.get("domain_tags") or [])[:4]) or "—"),
        ("期望接棒者", " / ".join((project.get("required_skills") or [])[:4]) or "有热情的续种人"),
    ]
    for label, value in info:
        d.text((120, y), label, font=f_label, fill=_C_GREEN)
        d.text((300, y - 3), str(value)[:22], font=f_value, fill=_C_INK)
        y += 56

    # 已有成果
    y += 16
    d.text((120, y), "前人留下的成果", font=f_label, fill=_C_GREEN)
    y += 48
    if achievements:
        for item in achievements[:4]:
            for j, line in enumerate(_wrap_text(str(item), f_small, W - 320)[:2]):
                prefix = "✦ " if j == 0 else "  "
                d.text((132, y), prefix + line, font=f_small, fill=_C_INK if j == 0 else _C_MUTED)
                y += 34
            y += 6
    else:
        d.text((132, y), "✦ 项目资料已完整封存，等待第一份新的生长", font=f_small, fill=_C_MUTED)
        y += 40

    # 寄语
    if message:
        quote_lines = _wrap_text(f"「{message}」", f_quote, W - 340)[:4]
        box_h = 56 + len(quote_lines) * 46
        top = min(H - 190, y + 18)
        d.rounded_rectangle([110, top, W - 110, top + box_h], radius=14, fill=(255, 253, 248))
        d.rectangle([110, top, 118, top + box_h], fill=_C_GOLD)
        qy = top + 24
        d.text((140, qy), "发起人寄语", font=f_label, fill=_C_GOLD)
        qy += 44
        for line in quote_lines:
            d.text((140, qy), line, font=f_quote, fill=_C_INK)
            qy += 46

    # 页脚
    d.line([120, H - 132, W - 120, H - 132], fill=_C_LINE, width=1)
    today = datetime.now().strftime("%Y年%m月%d日")
    _center(d, (W / 2, H - 110), today, f_foot, _C_MUTED)
    _center(d, (W / 2, H - 74), "知颜 · 第五季校园传承系统 监制", f_foot, _C_GREEN)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _render_poster(project: dict, achievements: list, votes: int,
                   handover_count: int, stage: str) -> bytes:
    """种子卡分享海报（现代简约 1080×1350，复用托付书渲染管线）"""
    from PIL import Image, ImageDraw

    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), _C_PAPER)
    d = ImageDraw.Draw(img)
    f_badge, f_title, f_sub = _font(30), _font(72), _font(28)
    f_body, f_label, f_chip, f_foot = _font(34), _font(26), _font(26), _font(24)

    d.rounded_rectangle([44, 44, W - 44, H - 44], radius=30, outline=_C_GREEN, width=3)

    # 四季圆点 + 第五季星
    dot_colors = [(168, 203, 178), (232, 182, 76), (214, 158, 106), (147, 177, 216)]
    for i, c in enumerate(dot_colors):
        d.ellipse([120 + i * 52, 108, 144 + i * 52, 132], fill=c)
    d.ellipse([120 + 4 * 52, 104, 152 + 4 * 52, 136], outline=_C_GOLD, width=3)

    y = 190
    if stage == "winter":
        badge = "❄️ 休眠种子 · 等待唤醒"
    elif stage == "fifth":
        badge = "✨ 第五季 · 重生进行中"
    else:
        badge = "🌱 项目种子 · 正在生长"
    d.text((120, y), badge, font=f_sub, fill=_C_GREEN)
    y += 64

    lines = _wrap_text(project.get("title") or "未命名项目", f_title, W - 240)[:2]
    for line in lines:
        d.text((116, y), line, font=f_title, fill=_C_INK)
        y += 88

    y += 12
    for line in _wrap_text(project.get("summary") or "一颗藏在校园记忆库里的种子。", f_body, W - 240)[:4]:
        d.text((120, y), line, font=f_body, fill=_C_MUTED)
        y += 50

    # 领域标签 chips
    y += 28
    d.text((120, y), "领域标签", font=f_label, fill=_C_GREEN)
    y += 46
    x = 120
    for tag in (project.get("domain_tags") or [])[:5]:
        text = f" {tag} "
        tw = f_chip.getlength(text) + 24
        if x + tw > W - 120:
            break
        d.rounded_rectangle([x, y, x + tw, y + 46], radius=23, outline=_C_GREEN, width=2)
        d.text((x + 12, y + 9), text, font=f_chip, fill=_C_GREEN)
        x += tw + 14

    # 数据行
    y += 92
    stats = f"已沉淀成果 {len(achievements)} 条 · 交接包 {handover_count} 份"
    if stage == "winter":
        stats += f" · 唤醒需求票 {votes} 票"
    d.rounded_rectangle([110, y - 12, W - 110, y + 52], radius=12, fill=_C_GREEN_LIGHT)
    d.text((132, y + 4), stats[:34], font=f_label, fill=_C_INK)

    # 唤醒成果预览
    y += 96
    if achievements:
        d.text((120, y), "它已经走到了这里", font=f_label, fill=_C_GREEN)
        y += 44
        for item in achievements[:3]:
            for j, line in enumerate(_wrap_text(str(item), f_foot, W - 320)[:1]):
                d.text((132, y), ("✦ " if j == 0 else "  ") + line, font=f_foot, fill=_C_INK)
                y += 34
            y += 6

    # CTA
    cta_top = max(y + 24, H - 330)
    d.rounded_rectangle([96, cta_top, W - 96, cta_top + 208], radius=20, fill=(61, 58, 52))
    qy = cta_top + 36
    _center(d, (W / 2, qy), "想让这颗种子重新发芽？", _font(40), (250, 247, 240))
    qy += 64
    for line in _wrap_text("到「第五季」和知颜聊聊——你的能力，可能正是它在等的下一双手。", f_sub, W - 300):
        _center(d, (W / 2, qy), line, f_sub, (168, 203, 178))
        qy += 42

    _center(d, (W / 2, H - 92), "第五季 · 续种 ｜ 校园未竟梦想的 AI 传承智能体", f_foot, _C_GREEN)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@tool
def generate_handover_certificate(nickname: str, project_id: int, message: str = "") -> str:
    """生成「毕业季·项目托付书」图片（现代简约风 PNG，含项目信息/前人成果/发起人寄语），
    上传对象存储后返回可访问链接。典型用途：负责人毕业/换届/寻找接棒人时，生成一张可分享的托付凭证。

    Args:
        nickname: 申请人昵称（须为该项目成员，通常为发起人或负责人）
        project_id: 项目id
        message: 发起人寄语（可选，一句想对接棒者说的话，将印在托付书上）
    """
    try:
        require_project_membership(project_id, nickname)
        project = require_project(project_id)
        names = fetch_user_names([project.get("founder_id"), project.get("owner_id")])
        founder = names.get(project.get("founder_id"), "—")
        owner = names.get(project.get("owner_id"), founder)
        handover = latest_handover(int(project_id))
        achievements = _parse_list_field(handover.get("achievements")) if handover else []
        stage = project.get("stage", "spring")
        png = _render_certificate(project, founder, owner, achievements, (message or "").strip(), stage)
        uploaded = _upload_image(png, f"fifth_season_certificate_{project_id}")
        return result_str(
            {
                "success": True,
                "project_title": project["title"],
                "stage": stage,
                "achievements_count": len(achievements),
                "image_url": uploaded["url"],
                "file_key": uploaded["file_key"],
                "message": (
                    "托付书已生成（图片链接 24 小时内有效）。请以 Markdown 图片语法 ![](url) 展示给用户，"
                    "并建议保存/分享给潜在接棒者。"
                ),
            }
        )
    except ValueError as e:
        return err_str(str(e))
    except APIError as e:
        return err_str(f"生成托付书失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(f"生成托付书失败: {e}")


@tool
def generate_seed_poster(project_id: int) -> str:
    """生成「种子卡分享海报」图片（现代简约风 PNG，含项目简介/领域标签/已有成果/唤醒引导），
    上传对象存储后返回可访问链接。典型用途：把休眠种子或进行中的项目分享到社交平台拉新、招募接棒者。

    Args:
        project_id: 项目id（休眠项目海报会带「等待唤醒」标识与需求数据）
    """
    try:
        project = require_project(project_id)
        client = get_supabase_client()
        handover = latest_handover(int(project_id))
        achievements = _parse_list_field(handover.get("achievements")) if handover else []
        handover_count = len(
            rows_of(
                client.table("fs_handover_packages").select("id").eq("project_id", int(project_id)).execute()
            )
        )
        votes = rows_of(
            client.table("fs_votes").select("id").eq("project_id", int(project_id)).execute()
        )
        stage = project.get("stage", "spring")
        png = _render_poster(project, achievements, len(votes), handover_count, stage)
        uploaded = _upload_image(png, f"fifth_season_poster_{project_id}")
        return result_str(
            {
                "success": True,
                "project_title": project["title"],
                "stage": stage,
                "image_url": uploaded["url"],
                "file_key": uploaded["file_key"],
                "message": "海报已生成（链接 24 小时内有效）。请以 ![](url) 展示，并鼓励用户分享扩散。",
            }
        )
    except ValueError as e:
        return err_str(str(e))
    except APIError as e:
        return err_str(f"生成海报失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(f"生成海报失败: {e}")


# ---------------------------------------------------------------------------
# 参考案例库：真实已完成项目（需求1）
# ---------------------------------------------------------------------------
@tool
def find_reference_cases(query: str = "", domain_tag: str = "", limit: int = 4) -> str:
    """检索「同类已完成项目」的真实参考案例（来自全国高校/公益机构的已落地项目，附可跳转网页链接）。
    当用户描述一个项目想法、或想知道「类似的事有没有人做成过」时调用；返回的每个案例都含
    真实成果数据与网页链接，供用户直接参考借鉴。

    Args:
        query: 项目想法或需求描述关键词（如"旧衣回收""书信陪伴留守儿童"），可留空
        domain_tag: 领域标签（如"公益服务""生态环保""心理健康""校园文化"），可留空
        limit: 最多返回几条，默认4
    """
    try:
        client = get_supabase_client()
        rows = rows_of(client.table("fs_reference_cases").select("*").execute())
        if not rows:
            return result_str({"success": False, "message": "参考案例库暂无数据"})

        q = (query or "").strip()
        tag = (domain_tag or "").strip()

        def score(row: dict) -> tuple:
            """标签命中优先，关键词命中标题/简介/机构次之"""
            tags = row.get("domain_tags") or []
            s = 0
            if tag:
                s += 8 if tag in tags else 0
            if q:
                for field in ("title", "summary", "org", "achievements"):
                    if q in str(row.get(field) or ""):
                        s += 3
                        break
                else:
                    hits = sum(1 for ch in q if len(ch) > 1 and any(ch in str(row.get(f) or "") for f in ("title", "summary")))
                    s += min(hits, 3)
            return (s, len(tags))

        ranked = sorted(rows, key=score, reverse=True)
        if tag or q:
            ranked = [r for r in ranked if score(r)[0] > 0] or ranked
        top = ranked[: max(1, min(int(limit), 8))]
        return result_str(
            {
                "success": True,
                "total": len(rows),
                "cases": [
                    {
                        "title": r["title"],
                        "org": r["org"],
                        "summary": r["summary"],
                        "domain_tags": r.get("domain_tags") or [],
                        "achievements": r.get("achievements"),
                        "award": r.get("award"),
                        "url": r["url"],
                    }
                    for r in top
                ],
                "message": "以上为真实已完成的参考案例。转述时请保留成果数字与奖项，用 Markdown 链接 [案例名](url) 让用户可直接跳转。",
            }
        )
    except APIError as e:
        return err_str(f"检索参考案例失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def search_github_projects(keywords: str, limit: int = 5) -> str:
    """从 GitHub 检索真实开源项目，为"找灵感/找同方向项目"的用户提供参考。适合三类场景：
    ① 用户想找同方向的开源项目学习；② 用户想接手某类项目但系统内没有合适的休眠项目；
    ③ 需要为没有交接包的项目整理可复用的开源资源。
    返回每个项目的名称/链接/简介/主语言/Star数/主题标签。拿到结果后，你（知颜）应按
    "项目方向、已解决的核心问题、可复用资源"三段为用户整理成轻量交接包口吻的介绍，并注明数据来自 GitHub。

    Args:
        keywords: 检索关键词（英文效果更好，如 "campus map" / "course scheduling" / "volunteer management"），必填
        limit: 返回项目数，默认 5，最大 10
    """
    keywords = (keywords or "").strip()
    if not keywords:
        return err_str("keywords 不能为空")
    limit = max(1, min(int(limit or 5), 10))
    try:
        import requests  # 局部导入，避免无网络环境下拖慢工具加载

        resp = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": keywords, "sort": "stars", "order": "desc", "per_page": limit},
            headers={"Accept": "application/vnd.github+json", "User-Agent": "fifth-season-agent"},
            timeout=15,
        )
        if resp.status_code != 200:
            return err_str(f"GitHub API 请求失败: HTTP {resp.status_code} {resp.text[:120]}")
        data = resp.json()
        items = data.get("items") or []
        projects = []
        for it in items[:limit]:
            projects.append(
                {
                    "name": it.get("full_name"),
                    "url": it.get("html_url"),
                    "direction": (it.get("description") or "无简介")[:120],
                    "language": it.get("language"),
                    "stars": it.get("stargazers_count"),
                    "topics": (it.get("topics") or [])[:8],
                    "solved_hint": "Star 数与主题标签反映的社区认可度，可作为该方向成熟度的参考",
                    "reusable": [it.get("html_url"), f"主语言: {it.get('language') or '未知'}"],
                }
            )
        return result_str(
            {
                "source": "GitHub Search API (api.github.com)",
                "query": keywords,
                "total_matches": data.get("total_count"),
                "count": len(projects),
                "projects": projects,
                "message": "以上为 GitHub 真实开源项目。请按'项目方向/已解决的核心问题/可复用资源'为用户整理，并明确注明数据来自 GitHub 公开仓库。",
            }
        )
    except requests.Timeout:
        return err_str("GitHub 请求超时（15秒），请稍后重试")
    except Exception as e:  # noqa: BLE001
        return err_str(f"GitHub 检索失败: {e}")

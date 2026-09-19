"""「第五季」校园板块工具：项目种子全生命周期（春/夏/秋/冬/第五季）状态机、
组队、动态日志、交接包、休眠唤醒与匹配留存。"""

import re
from datetime import date
from typing import Optional

from postgrest.exceptions import APIError

from storage.database.supabase_client import get_supabase_client
from tools.db_helpers import (
    VALID_TRANSITIONS,
    as_row,
    check_transition,
    decorate_project,
    err_str,
    fetch_user_names,
    get_user_id,
    latest_handover,
    now_utc,
    parse_json_list,
    require_project,
    require_project_membership,
    require_user_id,
    result_str,
    rows_of,
    safe_maybe_single,
)

from langchain.tools import tool


# 数据库规模尚小时，自然语言常与种子卡规范标签不一致。严格检索为空时，
# 用这组轻量同义主题词从真实项目中召回相邻方向，不生成或虚构项目。
_TOPIC_GROUPS = (
    {"公益", "志愿", "志愿者", "支教", "助学", "陪伴", "社区"},
    {"环保", "低碳", "循环", "回收", "旧物", "垃圾分类", "可持续"},
    {"心理", "心理健康", "情绪", "互助", "朋辈", "压力", "陪伴"},
    {"设计", "视觉", "摄影", "视频", "剪辑", "文创", "海报", "插画"},
    {"技术", "编程", "代码", "前端", "后端", "人工智能", "AI", "数据"},
    {"无障碍", "残障", "视障", "听障", "适老", "包容"},
    {"文化", "历史", "校史", "非遗", "口述", "档案", "记忆"},
    {"学习", "课程", "自习", "考研", "笔记", "学业", "阅读"},
    {"就业", "职业", "实习", "求职", "简历", "生涯"},
    {"运动", "体育", "跑步", "健身", "健康", "户外"},
    {"动物", "流浪动物", "猫", "宠物", "救助"},
    {"国际", "留学生", "跨文化", "语言", "交流"},
    {"校园服务", "地图", "导航", "食堂", "宿舍", "出行", "安全"},
    {"社团", "活动", "运营", "招新", "策划", "宣传"},
)


def _query_terms(*values: Optional[str]) -> set[str]:
    """把自然语言查询扩展为少量可解释的主题词。"""
    raw = " ".join(v.strip() for v in values if v and v.strip())
    if not raw:
        return set()
    terms = {t for t in re.split(r"[\s,，、/；;：:]+", raw) if len(t) >= 2}
    for group in _TOPIC_GROUPS:
        if any(word.lower() in raw.lower() for word in group):
            terms.update(group)
    return terms


def _related_score(project: dict, terms: set[str]) -> tuple[int, list[str]]:
    """为真实项目计算相邻主题得分，并返回可向用户解释的命中词。"""
    title = str(project.get("title") or "").lower()
    summary = str(project.get("summary") or "").lower()
    tags = " ".join(
        [str(x) for x in (project.get("domain_tags") or [])]
        + [str(x) for x in (project.get("required_skills") or [])]
    ).lower()
    score = 0
    hits: list[str] = []
    for term in terms:
        term_l = term.lower()
        part = 8 if term_l in title else 5 if term_l in tags else 3 if term_l in summary else 0
        if part:
            score += part
            if len(hits) < 3:
                hits.append(term)
    return score, hits


def assess_transfer_readiness(handover: Optional[dict], updates: list[dict]) -> dict:
    """按公开口径评估交接资料可用性，便于试点复核而非生成主观结论。"""
    sections = (
        "achievements",
        "experience",
        "pitfalls",
        "remaining_issues",
        "reusable_resources",
    )
    parsed = {key: parse_json_list((handover or {}).get(key)) for key in sections}
    resources = [str(item) for item in parsed["reusable_resources"]]
    def declarations(prefix):
        return [item[len(prefix):].strip() for item in resources if item.startswith(prefix)]

    validity = declarations("【资源有效期】")
    validity_ok = bool(validity)
    for value in validity:
        if value == "长期有效":
            continue
        try:
            validity_ok = validity_ok and date.fromisoformat(value) >= date.today()
        except ValueError:
            validity_ok = False
    checks = {
        "five_sections_complete": all(parsed[key] for key in sections),
        "has_process_trace": bool(updates),
        "authorization_declared": any(declarations("【授权范围】")),
        "validity_declared": validity_ok,
        "founder_rights_declared": any(declarations("【原团队权益】")),
    }
    weights = {
        "five_sections_complete": 50,
        "has_process_trace": 20,
        "authorization_declared": 10,
        "validity_declared": 10,
        "founder_rights_declared": 10,
    }
    score = sum(weights[key] for key, passed in checks.items() if passed)
    labels = {
        "five_sections_complete": "交接包五件套完整",
        "has_process_trace": "存在过程动态",
        "authorization_declared": "已声明成果授权范围",
        "validity_declared": "资源有效期格式正确且尚未到期",
        "founder_rights_declared": "已声明原团队权益保护",
    }
    blockers = [labels[key] for key, passed in checks.items() if not passed]
    return {
        "score": score,
        "level": "可接棒" if score == 100 else "需补充" if score >= 70 else "暂不建议接棒",
        "checks": checks,
        "blockers": blockers,
        "metric_definition": "五件套50分、过程动态20分、授权/有效期/原团队权益各10分；满分方可执行正式唤醒。",
    }


_GRADE_LADDER = {"大一": 10, "大二": 9, "大三": 6, "大四": 3, "研一": 8, "研二": 5, "研三": 2}


def score_project_match(profile: dict, project: dict) -> dict:
    """生成可审计的匹配分与解释；不读取未提供的信息，也不替代人工审批。

    六维评分：技能互补 40 / 兴趣与议题 25 / 年级阶梯 10 / 传承准备度 10 /
    社交邻近 8 / 时间投入 7。总分按已知维度归一化到百分制。
    年级阶梯：接棒长期项目需要足够的在校时间窗口，低年级接棒得分更高；
    社交邻近：与项目领域/院系背景重合可降低信任与沟通成本。
    """
    skills = {str(x).strip() for x in parse_json_list(profile.get("skill_tags")) if str(x).strip()}
    interests = {
        str(x).strip() for x in parse_json_list(profile.get("interest_tags")) if str(x).strip()
    }
    required = {
        str(x).strip() for x in parse_json_list(project.get("required_skills")) if str(x).strip()
    }
    domains = {
        str(x).strip() for x in parse_json_list(project.get("domain_tags")) if str(x).strip()
    }
    skill_hits = sorted(skills & required)
    interest_hits = sorted(interests & domains)

    dimensions = {
        "技能互补": round(40 * len(skill_hits) / max(1, len(required))),
        "兴趣与议题": round(25 * len(interest_hits) / max(1, len(domains))),
        "传承准备度": 10 if project.get("stage") in {"winter", "fifth"} else 5,
        "时间投入": None,
        "年级阶梯": None,
        "社交邻近": None,
    }

    # 时间投入：档案 bio 中声明的每周可投入小时数
    bio = str(profile.get("bio") or "")
    hours_match = re.search(r"(?:每周|周)[^\d]{0,8}(\d+(?:\.\d+)?)\s*小时", bio)
    if hours_match:
        hours = float(hours_match.group(1))
        dimensions["时间投入"] = min(7, round(hours / 3 * 7))

    # 年级阶梯：在校时间窗口决定能否承接跨周期项目
    grade = str(profile.get("grade") or "").strip()
    if grade in _GRADE_LADDER:
        dimensions["年级阶梯"] = _GRADE_LADDER[grade]
        if grade in {"大四", "研三"}:
            dimensions["年级阶梯"] = 3  # 临毕业接棒长期项目风险高，显式降档
    grade_note = None
    if grade in {"大四", "研三"}:
        grade_note = "接棒者临近毕业，在校时间窗口短，建议优先考虑轻量收尾型任务或与低年级同学组队"

    # 社交邻近：兴趣/技能与项目领域标签的重合广度（降低信任与沟通成本）
    if domains:
        proximity = len((interests | skills) & domains)
        dimensions["社交邻近"] = min(8, proximity * 4)

    scored = [v for v in dimensions.values() if v is not None]
    known_weight = 40 + 25 + 10 + (7 if dimensions["时间投入"] is not None else 0) \
        + (10 if dimensions["年级阶梯"] is not None else 0) + (8 if dimensions["社交邻近"] is not None else 0)
    raw_score = sum(scored)
    normalized = round(raw_score / known_weight * 100) if known_weight else 0
    gaps = sorted(required - skills)
    missing = [
        label for label, key in (("时间投入", "时间投入"), ("年级阶梯", "年级阶梯"), ("社交邻近", "社交邻近"))
        if dimensions[key] is None
    ]
    uncertainties = []
    if missing:
        uncertainties.append("档案缺少「" + "、".join(missing) + "」信息，对应维度未计入总分，接棒前请补充确认")
    if grade_note:
        uncertainties.append(grade_note)
    return {
        "score": normalized,
        "dimensions": dimensions,
        "evidence": {
            "技能命中": skill_hits,
            "兴趣命中": interest_hits,
            "待补能力": gaps[:4],
            "年级": grade or "未填写",
            "领域邻近": sorted((interests | skills) & domains)[:4],
        },
        "uncertainty": "；".join(uncertainties) if uncertainties else None,
        "decision_boundary": "推荐分仅供解释，不构成最终决定。接棒须走三步确认："
        "①接棒者提交接棒意愿 → ②原负责人核验交接包与授权范围并确认 → ③双方确认后执行正式唤醒。",
        "confirmation_flow": [
            "接棒者向知颜表达接棒意愿，系统调出交接包与准备度评估",
            "原负责人确认授权范围、资源有效期与原团队权益，必要时补充交接内容",
            "双方确认后发起唤醒投票并执行正式唤醒，交接过程记入传承故事",
        ],
    }


@tool
def create_project(
    nickname: str,
    title: str,
    summary: str,
    domain_tags: list[str],
    required_skills: list[str],
) -> str:
    """创建"项目种子卡"（春·萌芽）。调用前你必须先与用户澄清：项目要解决什么、属于什么领域、需要什么能力，
    并将用户的碎片化想法提炼为结构化字段后再调用本工具入库。

    Args:
        nickname: 发起人昵称（必须已建档）
        title: 项目标题（简明、可检索）
        summary: 项目简介（目标/背景/初步计划，2~5 句）
        domain_tags: 领域标签列表，如["公益","无障碍","校园服务"]
        required_skills: 项目所需能力标签列表，如["测绘设计","实地调研"]
    """
    title = (title or "").strip()
    if not title:
        return err_str("项目标题不能为空")
    try:
        uid = require_user_id(nickname)
        client = get_supabase_client()
        resp = (
            client.table("fs_projects")
            .insert(
                {
                    "title": title,
                    "summary": (summary or "").strip() or None,
                    "domain_tags": [t.strip() for t in (domain_tags or []) if t and t.strip()],
                    "required_skills": [
                        s.strip() for s in (required_skills or []) if s and s.strip()
                    ],
                    "stage": "spring",
                    "founder_id": uid,
                    "owner_id": uid,
                }
            )
            .execute()
        )
        project = decorate_project(as_row(resp))
        # 发起人自动成为项目首位成员（负责人）
        client.table("fs_project_members").insert(
            {"project_id": project["id"], "user_id": uid, "role": "发起人/负责人"}
        ).execute()
        return result_str(
            {
                "success": True,
                "action": "create",
                "project": project,
                "message": (
                    f"项目种子「{project['title']}」已播下（春·萌芽），"
                    f"项目编号 #{project['id']}。发起人已自动加入为负责人。"
                ),
            }
        )
    except APIError as e:
        return err_str(f"创建项目失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def search_projects(
    keyword: Optional[str] = None,
    stage: Optional[str] = None,
    domain_tag: Optional[str] = None,
    owner_nickname: Optional[str] = None,
    matcher_nickname: Optional[str] = None,
    limit: int = 5,
) -> str:
    """检索项目种子库（支持标题/简介关键词、阶段、领域标签、负责人过滤）。
    典型用途：用户想找项目时按意向检索；查看休眠项目传 stage="winter"；查看某人名下项目传 owner_nickname。
    不适用：把一个想法立成新项目请用 create_project；查看某个项目的完整资料（成员/动态/交接包）
    请用 get_project_detail；判断哪些项目需要关注请用 get_project_health。

    Args:
        keyword: 关键词，模糊匹配标题或简介（可选）
        stage: 项目阶段过滤 spring/summer/autumn/winter/fifth（可选）
        domain_tag: 领域标签精确匹配（可选）
        owner_nickname: 负责人昵称，过滤某用户名下的项目（可选，用于「我的项目」查询）
        matcher_nickname: 需要进行可解释匹配的用户昵称（可选，用户须已建档）
        limit: 最多返回条数，默认10
    """
    try:
        client = get_supabase_client()
        query = client.table("fs_projects").select(
            "id, title, summary, domain_tags, required_skills, stage, "
            "founder_id, owner_id, hibernate_reason, hibernate_at, created_at, updated_at"
        )
        if keyword and keyword.strip():
            kw = keyword.strip().replace(",", "").replace("*", "")
            query = query.or_(f"title.ilike.*{kw}*,summary.ilike.*{kw}*")
        if stage:
            query = query.eq("stage", stage)
        if domain_tag and domain_tag.strip():
            query = query.contains("domain_tags", [domain_tag.strip()])
        if owner_nickname and owner_nickname.strip():
            oid = get_user_id(owner_nickname.strip())
            if oid is None:
                return result_str(
                    {
                        "success": True,
                        "action": "search",
                        "total": 0,
                        "projects": [],
                        "hint": f"「{owner_nickname.strip()}」尚未建档，无法查询其名下项目",
                    }
                )
            query = query.eq("owner_id", oid)
        result_limit = max(1, min(int(limit), 50))
        resp = query.order("updated_at", desc=True).limit(result_limit).execute()
        projects = [decorate_project(p) for p in rows_of(resp)]
        match_mode = "exact"

        # 保留阶段/负责人约束，放宽关键词与领域标签做同义主题召回；仍无相关项时，
        # 返回少量近期真实项目供探索，避免对话以一句“没有相关项目”结束。
        if not projects and (keyword or domain_tag):
            fallback = client.table("fs_projects").select(
                "id, title, summary, domain_tags, required_skills, stage, "
                "founder_id, owner_id, hibernate_reason, hibernate_at, created_at, updated_at"
            )
            if stage:
                fallback = fallback.eq("stage", stage)
            if owner_nickname and owner_nickname.strip():
                fallback = fallback.eq("owner_id", oid)
            candidates = [
                decorate_project(p)
                for p in rows_of(fallback.order("updated_at", desc=True).limit(50).execute())
            ]
            terms = _query_terms(keyword, domain_tag)
            scored = []
            for project in candidates:
                score, hits = _related_score(project, terms)
                if score > 0:
                    project["match_score"] = score
                    project["match_reason"] = "相邻主题：" + " / ".join(hits)
                    scored.append((score, project))
            scored.sort(key=lambda item: item[0], reverse=True)
            if scored:
                projects = [item[1] for item in scored[:result_limit]]
                match_mode = "related"
            elif candidates:
                projects = candidates[: min(result_limit, 5)]
                for project in projects:
                    project["match_reason"] = "暂无精确命中，作为近期可探索项目展示"
                match_mode = "explore"
        names = fetch_user_names(
            [p["founder_id"] for p in projects] + [p["owner_id"] for p in projects]
        )
        for p in projects:
            p["founder_nickname"] = names.get(p["founder_id"])
            p["owner_nickname"] = names.get(p["owner_id"])

        # 可解释匹配：只使用真实档案字段；时间投入未结构化时明确标为待确认，
        # 不用模型臆测补分。分数用于排序与解释，不自动决定入组或接棒。
        if matcher_nickname and matcher_nickname.strip():
            profile_resp = (
                client.table("fs_users")
                .select("nickname, grade, major, skill_tags, interest_tags, bio")
                .eq("nickname", matcher_nickname.strip())
                .limit(1)
                .execute()
            )
            profile_rows = rows_of(profile_resp)
            if not profile_rows:
                return err_str(f"「{matcher_nickname.strip()}」尚未建档，无法进行可解释匹配")
            profile = profile_rows[0]
            for project in projects:
                project["explainable_match"] = score_project_match(profile, project)
            projects.sort(
                key=lambda p: p.get("explainable_match", {}).get("score", 0),
                reverse=True,
            )
        return result_str(
            {
                "success": True,
                "action": "search",
                "total": len(projects),
                "projects": projects,
                "match_mode": match_mode,
                "matcher_nickname": matcher_nickname.strip() if matcher_nickname else None,
                "match_policy": (
                    "六维评分：技能互补40+兴趣与议题25+年级阶梯10+传承准备度10+社交邻近8+时间投入7；"
                    "未知维度不补分并显式披露；结果仅作推荐解释，接棒须走三步确认"
                    "（接棒意愿→原负责人核验授权→双方确认后唤醒）"
                    if matcher_nickname else None
                ),
                "hint": (
                    "未找到精确匹配，以下为真实项目库中的相邻主题推荐；请明确说明并询问用户是否愿意拓宽方向"
                    if match_mode == "related"
                    else "未找到精确或同义主题匹配，以下为近期真实项目供探索；不要表述为精确匹配"
                    if match_mode == "explore"
                    else "查看项目完整资料（成员/动态/交接包）请用 get_project_detail"
                ),
            }
        )
    except APIError as e:
        return err_str(f"检索项目失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def get_project_detail(project_id: int) -> str:
    """获取项目全景资料：种子卡基本信息 + 成员列表 + 最近动态 + 最新交接包。
    休眠项目被唤醒前，必须用它向接力者完整展示项目全部资料。

    Args:
        project_id: 项目id
    """
    try:
        project = decorate_project(require_project(project_id))
        client = get_supabase_client()
        members = rows_of(
            client.table("fs_project_members")
            .select("id, user_id, role, joined_at")
            .eq("project_id", int(project_id))
            .order("joined_at")
            .limit(50)
            .execute()
        )
        updates = rows_of(
            client.table("fs_project_updates")
            .select("id, author_id, content, stage, created_at")
            .eq("project_id", int(project_id))
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        handover = latest_handover(int(project_id))
        if handover:
            handover = dict(handover)
            for field in (
                "achievements",
                "experience",
                "pitfalls",
                "remaining_issues",
                "reusable_resources",
            ):
                handover[field] = parse_json_list(handover.get(field))
        transfer_readiness = assess_transfer_readiness(handover, updates)
        names = fetch_user_names(
            [project["founder_id"], project["owner_id"]]
            + [m["user_id"] for m in members]
            + [u["author_id"] for u in updates]
        )
        project["founder_nickname"] = names.get(project["founder_id"])
        project["owner_nickname"] = names.get(project["owner_id"])
        for m in members:
            m["nickname"] = names.get(m["user_id"])
        for u in updates:
            u["author_nickname"] = names.get(u["author_id"])
        return result_str(
            {
                "success": True,
                "action": "detail",
                "project": project,
                "members": members,
                "recent_updates": updates,
                "handover_package": handover,
                "transfer_readiness": transfer_readiness,
            }
        )
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def update_project(
    project_id: int,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    domain_tags: Optional[list[str]] = None,
    required_skills: Optional[list[str]] = None,
) -> str:
    """编辑项目种子卡信息（至少提供一个修改字段）。

    Args:
        project_id: 项目id
        title: 新标题（可选）
        summary: 新简介（可选）
        domain_tags: 新领域标签列表（可选，整体替换）
        required_skills: 新所需能力列表（可选，整体替换）
    """
    try:
        require_project(project_id)
        payload = {}
        if title is not None and title.strip():
            payload["title"] = title.strip()
        if summary is not None:
            payload["summary"] = summary.strip() or None
        if domain_tags is not None:
            payload["domain_tags"] = [t.strip() for t in domain_tags if t and t.strip()]
        if required_skills is not None:
            payload["required_skills"] = [
                s.strip() for s in required_skills if s and s.strip()
            ]
        if not payload:
            return err_str("update_project 至少需要提供一个修改字段")
        resp = (
            get_supabase_client()
            .table("fs_projects")
            .update(payload)
            .eq("id", int(project_id))
            .execute()
        )
        return result_str(
            {"success": True, "action": "update", "project": decorate_project(as_row(resp))}
        )
    except APIError as e:
        return err_str(f"更新项目失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def advance_project_stage(
    project_id: int,
    target_stage: str,
    nickname: str,
    reason: Optional[str] = None,
) -> str:
    """推进项目四季生命周期：spring→summer(进入执行)、summer→autumn(沉淀)、autumn→summer(继续推进)、
    活跃阶段→winter(休眠归档，需reason)、fifth→summer(接棒后重启)。
    注意：唤醒休眠项目（winter→fifth）必须使用 awaken_project 工具完成。

    Args:
        project_id: 项目id
        target_stage: 目标阶段 spring/summer/autumn/winter/fifth
        nickname: 操作人昵称
        reason: 流转原因（流转到 winter 时必填：休眠原因，如毕业/换届/时间冲突）
    """
    target = (target_stage or "").strip().lower()
    try:
        project = require_project(project_id)
        uid = require_project_membership(project_id, nickname)
        current = project["stage"]

        if current == "winter" and target == "fifth":
            return err_str("唤醒休眠项目请使用 awaken_project 工具（需要记录接力人与匹配理由）")

        ok, note = check_transition(current, target)
        if not ok:
            return err_str(note)

        payload = {"stage": target}
        if target == "winter":
            if not reason or not reason.strip():
                return err_str("项目休眠必须填写休眠原因（如团队毕业/换届/时间冲突）")
            payload["hibernate_reason"] = reason.strip()
            payload["hibernate_at"] = now_utc().isoformat()

        resp = (
            get_supabase_client()
            .table("fs_projects")
            .update(payload)
            .eq("id", int(project_id))
            .execute()
        )
        updated = decorate_project(as_row(resp))
        # 记录一条阶段流转动态
        get_supabase_client().table("fs_project_updates").insert(
            {
                "project_id": int(project_id),
                "author_id": uid,
                "content": f"项目阶段流转：{note}"
                + (f"（原因：{reason.strip()}）" if target == "winter" and reason else ""),
                "stage": target,
            }
        ).execute()
        return result_str(
            {
                "success": True,
                "action": "advance_stage",
                "project": updated,
                "message": f"项目「{updated['title']}」已进入 {updated['stage_name']} 阶段",
            }
        )
    except APIError as e:
        return err_str(f"阶段流转失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def add_project_update(project_id: int, nickname: str, content: str) -> str:
    """为项目记录一条进展动态（夏·生长的过程记录，也是秋·沉淀总结的原始素材）。

    Args:
        project_id: 项目id
        nickname: 记录人昵称（项目成员或负责人）
        content: 动态内容（进展/成果/遇到的问题）
    """
    content = (content or "").strip()
    if not content:
        return err_str("动态内容不能为空")
    try:
        project = require_project(project_id)
        uid = require_user_id(nickname)
        resp = (
            get_supabase_client()
            .table("fs_project_updates")
            .insert(
                {
                    "project_id": int(project_id),
                    "author_id": uid,
                    "content": content,
                    "stage": project["stage"],
                }
            )
            .execute()
        )
        return result_str(
            {
                "success": True,
                "action": "add_update",
                "update": as_row(resp),
                "message": "项目动态已记录",
            }
        )
    except APIError as e:
        return err_str(f"记录动态失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def add_project_member(project_id: int, nickname: str, role: str) -> str:
    """为项目添加成员（夏·生长组队结果）。AI 完成互补度评估并经用户确认后调用。

    Args:
        project_id: 项目id
        nickname: 新成员昵称（必须已建档）
        role: 成员角色，如"测绘主力/调研执行/设计负责人"
    """
    role = (role or "").strip() or "成员"
    try:
        require_project(project_id)
        uid = require_user_id(nickname)
        client = get_supabase_client()
        existed = safe_maybe_single(
            client.table("fs_project_members")
            .select("id")
            .eq("project_id", int(project_id))
            .eq("user_id", uid)
        )
        if existed:
            return err_str(f"「{nickname}」已是项目成员，无需重复添加")
        resp = (
            client.table("fs_project_members")
            .insert({"project_id": int(project_id), "user_id": uid, "role": role})
            .execute()
        )
        return result_str(
            {
                "success": True,
                "action": "add_member",
                "member": {**as_row(resp), "nickname": nickname},
                "message": f"「{nickname}」已加入项目，角色：{role}",
            }
        )
    except APIError as e:
        return err_str(f"添加成员失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def save_handover_package(
    project_id: int,
    achievements: list[str],
    experience: list[str],
    pitfalls: list[str],
    remaining_issues: list[str],
    reusable_resources: list[str],
    authorization_scope: Optional[str] = None,
    resource_valid_until: Optional[str] = None,
    founder_rights: Optional[str] = None,
) -> str:
    """保存项目交接包（秋·沉淀）。调用前你必须先阅读项目全部动态（get_project_detail），
    再将项目成果、执行经验、踩坑总结、遗留问题、可复用资源提炼为五段式结构化清单。
    每段至少 1 条，基于真实项目动态提炼，禁止编造。另须明确成果授权范围、资源有效期和原团队权益保护；
    三项治理声明会写入交接包并在唤醒前自动校验。

    Args:
        project_id: 项目id
        achievements: 项目成果列表
        experience: 执行经验列表
        pitfalls: 踩坑总结列表
        remaining_issues: 遗留问题/未完成任务列表
        reusable_resources: 可复用资源列表（资料/联系人/渠道等）
        authorization_scope: 成果授权范围，如“仅校内公益使用，禁止商业传播”
        resource_valid_until: 资源有效期，YYYY-MM-DD 或“长期有效”
        founder_rights: 原团队权益保护，如“保留署名；重大改编需再次确认”
    """
    try:
        require_project(project_id)
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
                return err_str(f"交接包「{k}」段不能为空，请基于项目动态提炼至少 1 条")
            clean[k] = items
        clean["reusable_resources"].extend(
            [
                f"【授权范围】{governance['authorization_scope']}",
                f"【资源有效期】{governance['resource_valid_until']}",
                f"【原团队权益】{governance['founder_rights']}",
            ]
        )
        import json as _json

        resp = (
            get_supabase_client()
            .table("fs_handover_packages")
            .insert({"project_id": int(project_id), **{k: _json.dumps(v, ensure_ascii=False) for k, v in clean.items()}})
            .execute()
        )
        return result_str(
            {
                "success": True,
                "action": "save_handover",
                "package_id": as_row(resp)["id"],
                "sections": {k: len(v) for k, v in clean.items()},
                "governance": governance,
                "message": "交接包已生成并归档，后续接棒者可通过 get_project_detail 完整查看",
            }
        )
    except APIError as e:
        return err_str(f"保存交接包失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def awaken_project(project_id: int, successor_nickname: str, match_reason: str) -> str:
    """唤醒休眠项目并完成接力（第五季·重生，核心传承动作）。
    前置条件：项目处于 winter 休眠阶段；接棒者已建档；你已完成匹配评估并向接棒者展示完整项目资料。
    执行动作：项目进入 fifth 阶段、负责人变更为接棒者、接棒者加入成员、写入唤醒记录、记录重生动态。

    Args:
        project_id: 休眠项目id
        successor_nickname: 接棒者昵称（必须已建档）
        match_reason: 匹配理由（兴趣/能力与项目的契合说明，将写入唤醒记录用于传承溯源）
    """
    match_reason = (match_reason or "").strip()
    if not match_reason:
        return err_str("唤醒项目必须提供匹配理由")
    try:
        project = require_project(project_id)
        successor_id = require_user_id(successor_nickname)
        if project["stage"] != "winter":
            return err_str(
                f"项目「{project['title']}」当前处于 {project['stage']} 阶段，仅 winter(冬·蛰伏) 状态的项目可被唤醒"
            )
        client = get_supabase_client()
        handover = latest_handover(int(project_id))
        updates = rows_of(
            client.table("fs_project_updates")
            .select("id")
            .eq("project_id", int(project_id))
            .limit(1)
            .execute()
        )
        readiness = assess_transfer_readiness(handover, updates)
        if readiness["score"] < 100:
            return err_str(
                "项目尚未通过接续准备度校验，暂不能正式唤醒。待补项："
                + "、".join(readiness["blockers"])
            )
        resp = (
            client.table("fs_projects")
            .update({"stage": "fifth", "owner_id": successor_id})
            .eq("id", int(project_id))
            .execute()
        )
        updated = decorate_project(as_row(resp))
        # 接棒者加入成员（若尚未是成员）
        existed = safe_maybe_single(
            client.table("fs_project_members")
            .select("id")
            .eq("project_id", int(project_id))
            .eq("user_id", successor_id)
        )
        if not existed:
            client.table("fs_project_members").insert(
                {"project_id": int(project_id), "user_id": successor_id, "role": "接棒负责人"}
            ).execute()
        # 写入唤醒记录（第五季传承溯源的核心数据）
        awaken_resp = (
            client.table("fs_awaken_records")
            .insert(
                {
                    "project_id": int(project_id),
                    "successor_id": successor_id,
                    "match_reason": match_reason,
                }
            )
            .execute()
        )
        awaken_row = as_row(awaken_resp) or {}
        # 自动生成「传承故事卡」挂上故事墙（best-effort，失败不影响唤醒）
        from tools.legacy_tools import record_relay_story

        record_relay_story(
            project,
            successor_nickname,
            match_reason,
            awaken_row.get("id"),
        )
        # 记录重生动态
        client.table("fs_project_updates").insert(
            {
                "project_id": int(project_id),
                "author_id": successor_id,
                "content": f"项目被「{successor_nickname}」唤醒接棒（第五季·重生）。匹配理由：{match_reason}",
                "stage": "fifth",
            }
        ).execute()
        return result_str(
            {
                "success": True,
                "action": "awaken",
                "project": updated,
                "successor": successor_nickname,
                "match_reason": match_reason,
                "transfer_readiness": readiness,
                "story_created": True,
                "message": (
                    f"休眠项目「{updated['title']}」已被唤醒，"
                    f"进入第五季·重生阶段，负责人已变更为「{successor_nickname}」，"
                    f"传承故事卡已自动挂上故事墙。"
                    f"接棒后可引导团队推进执行（advance_project_stage → summer）。"
                ),
            }
        )
    except APIError as e:
        return err_str(f"唤醒项目失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def save_match_log(
    match_type: str,
    user_nickname: str,
    project_id: Optional[int] = None,
    matched_user_nickname: Optional[str] = None,
    match_score: Optional[float] = None,
    match_reason: Optional[str] = None,
) -> str:
    """留存一次双向匹配结果（项目找人/人找项目/找伙伴），用于产品效果验证与数据沉淀。
    每当你完成一次匹配评估并推荐给用户时调用。

    Args:
        match_type: 匹配类型 user_to_project(人找项目)/project_to_user(项目找人)/partner(为项目找伙伴)
        user_nickname: 发起匹配的用户昵称
        project_id: 涉及项目id（partner/user_to_project 场景必填）
        matched_user_nickname: 被匹配的用户昵称（partner 场景必填）
        match_score: 匹配分 0-100（你的综合评估）
        match_reason: 匹配理由
    """
    match_type = (match_type or "").strip().lower()
    if match_type not in {"user_to_project", "project_to_user", "partner"}:
        return err_str("match_type 仅支持 user_to_project/project_to_user/partner")
    try:
        uid = require_user_id(user_nickname)
        payload = {"match_type": match_type, "user_id": uid}
        if project_id is not None:
            require_project(project_id)
            payload["project_id"] = int(project_id)
        if matched_user_nickname:
            payload["matched_user_id"] = require_user_id(matched_user_nickname)
        if match_score is not None:
            payload["match_score"] = max(0.0, min(float(match_score), 100.0))
        if match_reason:
            payload["match_reason"] = match_reason.strip()
        resp = get_supabase_client().table("fs_match_logs").insert(payload).execute()
        return result_str(
            {
                "success": True,
                "action": "save_match_log",
                "log_id": as_row(resp)["id"],
                "message": "匹配结果已留存",
            }
        )
    except APIError as e:
        return err_str(f"留存匹配日志失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def get_reminders(nickname: str) -> str:
    """获取场景化提醒素材（用户发起对话时调用）：临期/搁置的待办 + 名下休眠中的项目。
    返回原始数据，由你在应答中转化为自然、有温度的提醒文案。

    Args:
        nickname: 用户昵称
    """
    try:
        uid = require_user_id(nickname)
        client = get_supabase_client()
        todos = rows_of(
            client.table("fs_todos")
            .select("id, title, due_at, status, project_id, created_at")
            .eq("user_id", uid)
            .in_("status", ["pending", "doing"])
            .order("due_at", desc=False)
            .limit(20)
            .execute()
        )
        dormant = rows_of(
            client.table("fs_projects")
            .select(
                "id, title, stage, hibernate_reason, hibernate_at, updated_at"
            )
            .eq("owner_id", uid)
            .eq("stage", "winter")
            .order("hibernate_at", desc=True)
            .limit(10)
            .execute()
        )
        now = now_utc()
        for t in todos:
            from tools.db_helpers import parse_iso

            due = parse_iso(t.get("due_at") or "")
            if due:
                delta_days = (due - now).total_seconds() / 86400
                if delta_days < 0:
                    t["urgency"] = "已过期"
                elif delta_days <= 3:
                    t["urgency"] = "3天内到期"
                else:
                    t["urgency"] = None
        reminders = {
            "open_todos": todos,
            "dormant_projects": [
                {**p, "stage_name": "冬·蛰伏"} for p in dormant
            ],
            "hint": "请将临期待办与休眠项目转化为自然提醒；休眠项目可提示用户寻找接棒者或推荐给匹配的新同学",
        }
        return result_str({"success": True, "action": "get_reminders", **reminders})
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))


@tool
def school_issue_insight(stage: Optional[str] = None) -> str:
    """生成「校园社会议题洞察报告」：统计哪些社会议题被反复提出、却始终无人完成接棒。
    聚合全量项目种子库的领域标签(domain_tags)与阶段(stage)分布，识别「被反复提及却仍处于休眠/未推进」的议题，
    供学校、社团做传承决策与选题参考。

    Args:
        stage: 可选，只看某一阶段的项目（如传 "winter" 只看休眠项目里反复出现的议题）；默认全量聚合
    """
    try:
        client = get_supabase_client()
        query = client.table("fs_projects").select("id, title, domain_tags, stage")
        if stage and stage.strip():
            query = query.eq("stage", stage.strip())
        projects = rows_of(query.execute())

        agg: dict[str, dict] = {}
        for p in projects:
            for raw in p.get("domain_tags") or []:
                tag = (raw or "").strip()
                if not tag:
                    continue
                bucket = agg.setdefault(tag, {"total": 0, "stages": {}})
                bucket["total"] += 1
                st = p.get("stage") or "spring"
                bucket["stages"][st] = bucket["stages"].get(st, 0) + 1

        issues = []
        for tag, info in agg.items():
            stages = info["stages"]
            dormant = stages.get("winter", 0)
            unfinished = dormant + stages.get("spring", 0)
            issues.append(
                {
                    "tag": tag,
                    "total": info["total"],
                    "dormant": dormant,
                    "ongoing": stages.get("summer", 0) + stages.get("autumn", 0),
                    "awakened": stages.get("fifth", 0),
                    "unfinished": unfinished,
                }
            )
        # 被反复提出（total 高）且始终未完成（unfinished 高）的议题排前
        issues.sort(key=lambda x: (-x["total"], -x["unfinished"]))

        return result_str(
            {
                "success": True,
                "action": "school_issue_insight",
                "total_projects": len(projects),
                "issues": issues,
                "hint": (
                    "total 为该议题被提出的项目数，unfinished 为休眠(冬)+未推进(春)的项目数；"
                    "二者都高即「被反复提出却始终无人完成」的议题。请用有温度的方式转述为传承报告，"
                    "并指出每个议题最值得被接棒的方向。"
                ),
            }
        )
    except APIError as e:
        return err_str(f"生成议题洞察失败: {e.message}")
    except Exception as e:  # noqa: BLE001
        return err_str(str(e))

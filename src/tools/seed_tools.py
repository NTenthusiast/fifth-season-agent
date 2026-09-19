"""v8.0 种子卡生态工具：GitHub 导入、上传文件读取、个人画像、种子对匹配、团队总览。"""
import json
import os
import re
from typing import Optional

import requests
from langchain.tools import tool

from tools.db_helpers import (
    err_str,
    get_supabase_client,
    require_user_id,
    rows_of,
)

UPLOAD_DIR = "/tmp/fs_uploads"


def _norm_tags(raw) -> list:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = [t.strip() for t in re.split(r"[,，、\s]+", raw) if t.strip()]
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    return [str(t).strip() for t in raw if t and str(t).strip()][:6]


def _legacy_code_of(client, uid: int) -> str:
    rows = rows_of(
        client.table("fs_users").select("legacy_code").eq("id", uid).execute()
    )
    return (rows[0].get("legacy_code") or "000000") if rows else "000000"


@tool
def import_from_github(url: str, nickname: str) -> str:
    """导入 GitHub 仓库自动整理建档素材：抓取仓库简介、语言、Star、README 摘要与目录结构，
    返回结构化素材供你（知颜）进一步整理成项目档案/种子卡。
    用户给出 GitHub 链接想"导入代码建档"时调用。抓取失败会如实返回错误。

    Args:
        url: GitHub 仓库地址（https://github.com/用户名/仓库名 或含子路径）
        nickname: 当前用户昵称
    """
    m = re.search(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", url or "")
    if not m:
        return err_str("无法从链接中识别 GitHub 仓库（期望形如 https://github.com/用户名/仓库名）")
    owner, repo = m.group(1), m.group(2).removesuffix(".git")
    ctx = None
    try:
        from coze_coding_utils.log.write_log import request_context

        ctx = request_context.get()
    except Exception:
        ctx = None
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "fifth-season-agent"}
    ctx_headers = getattr(ctx, "headers", None) if ctx else None
    if ctx_headers:
        auth = ctx_headers.get("authorization") or ctx_headers.get("Authorization")
        if auth:
            headers["Authorization"] = auth
    try:
        info = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=15
        )
        if info.status_code == 404:
            return err_str(f"仓库 {owner}/{repo} 不存在或已设为私有")
        info.raise_for_status()
        meta = info.json()
        readme_raw = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/readme",
            headers={**headers, "Accept": "application/vnd.github.raw+json"},
            timeout=15,
        )
        readme = ""
        if readme_raw.status_code == 200:
            readme = (readme_raw.text or "")[:3000]
        return json.dumps(
            {
                "success": True,
                "repo": f"{owner}/{repo}",
                "title": meta.get("name") or repo,
                "description": meta.get("description") or "",
                "language": meta.get("language"),
                "stars": meta.get("stargazers_count"),
                "topics": meta.get("topics") or [],
                "default_branch": meta.get("default_branch"),
                "readme_excerpt": readme,
                "url": meta.get("html_url"),
                "hint": "请基于以上素材整理：项目定位/已解决的核心问题/可复用资源，向用户确认不明晰处后建档",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return err_str(f"GitHub 抓取失败：{e}")


@tool
def read_upload(file_id: str, nickname: str) -> str:
    """读取用户上传文件的解析全文（用户在网页上传文件后会让知颜整理建档，此时调用本工具读取内容）。
    支持在 /tmp/fs_uploads 下登记过的 txt/md/csv/json/pdf/docx 文件。

    Args:
        file_id: 上传文件标识（如 up_ab12cd）
        nickname: 当前用户昵称
    """
    safe = re.sub(r"[^A-Za-z0-9_-]", "", file_id or "")
    meta_path = os.path.join(UPLOAD_DIR, f"{safe}.json")
    if not safe or not os.path.exists(meta_path):
        return err_str(f"找不到上传文件 {file_id}，请让用户在网页重新上传")
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return json.dumps(
            {
                "success": True,
                "file_name": meta.get("name"),
                "file_type": meta.get("type"),
                "chars": meta.get("chars"),
                "content": (meta.get("content") or "")[:12000],
                "hint": "请通读后提炼：项目定位/已解决的核心问题/可复用资源，向用户确认不明晰处后建档",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return err_str(f"读取上传文件失败：{e}")


@tool
def upsert_profile(
    nickname: str,
    traits: Optional[str] = None,
    strengths: Optional[str] = None,
    story: Optional[str] = None,
    goals: Optional[str] = None,
    profile_public: Optional[bool] = None,
) -> str:
    """生成/更新当前用户的个人档案画像（fs_users.persona）。首次对话完成信息收集后调用一次；
    用户要求修改画像或公开状态时再次调用。画像内容用第二人称"你"温和描述，每段 80 字内。

    Args:
        nickname: 当前用户昵称
        traits: 性格特质（如：温和细致，喜欢把复杂问题拆成小步骤）
        strengths: 技能专长（如：Python 数据处理、活动统筹）
        story: 经历故事（一句话概括用户的校园经历亮点）
        goals: 当前方向/目标（如：想把标本社做起来）
        profile_public: 是否公开画像（用户明确同意才 true；不传则保持原状）
    """
    try:
        client = get_supabase_client()
        uid = require_user_id(nickname)
        rows = rows_of(
            client.table("fs_users").select("persona, profile_public").eq("id", uid).execute()
        )
        old = {}
        if rows and rows[0].get("persona"):
            raw = rows[0]["persona"]
            old = raw if isinstance(raw, dict) else json.loads(raw)
        persona = {
            "traits": traits or old.get("traits") or "",
            "strengths": strengths or old.get("strengths") or "",
            "story": story or old.get("story") or "",
            "goals": goals or old.get("goals") or "",
        }
        patch: dict = {"persona": json.dumps(persona, ensure_ascii=False)}
        if profile_public is not None:
            patch["profile_public"] = bool(profile_public)
        client.table("fs_users").update(patch).eq("id", uid).execute()
        pub = patch.get("profile_public", (rows[0].get("profile_public") if rows else False))
        return json.dumps(
            {
                "success": True,
                "action": "upsert_profile",
                "persona": persona,
                "profile_public": pub,
                "message": "画像已更新" + ("并已公开（他人可在项目发起人处查看）" if pub else "（当前仅自己可见）"),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return err_str(f"画像更新失败：{e}")


@tool
def match_seed_partners(nickname: str, focus: Optional[str] = None) -> str:
    """种子对匹配：以当前用户的技能/项目为基准，寻找能力互补的搭档与可联手的项目
    （我缺的技能对方正好有）。返回互补度最高的候选（含昵称、画像摘要-if公开、互补点说明），
    供知颜向用户解释并征得同意后用 send_message 主动牵线留言。

    Args:
        nickname: 当前用户昵称
        focus: 用户补充的匹配关注点（如"想做环保方向"），可选
    """
    try:
        client = get_supabase_client()
        uid = require_user_id(nickname)
        me_rows = rows_of(
            client.table("fs_users")
            .select("nickname, skill_tags, interest_tags, persona, profile_public")
            .eq("id", uid)
            .execute()
        )
        if not me_rows:
            return err_str("未找到你的档案")
        me = me_rows[0]

        def _tags(v):
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    v = [v]
            return {str(t).strip() for t in (v or []) if t and str(t).strip()}

        my_skills = _tags(me.get("skill_tags"))
        my_interests = _tags(me.get("interest_tags")) | _tags(focus)

        # 我的项目所需但我不掌握的技能 = 缺口
        my_projects = rows_of(
            client.table("fs_projects")
            .select("id, title, required_skills, stage")
            .eq("owner_id", uid)
            .execute()
        )
        gap: set = set()
        for p in my_projects:
            gap |= _tags(p.get("required_skills")) - my_skills

        # 伙伴候选：技能命中我的缺口或兴趣同频
        others = rows_of(
            client.table("fs_users")
            .select("id, nickname, grade, major, skill_tags, interest_tags, persona, profile_public")
            .neq("id", uid)
            .execute()
        )
        cands = []
        for o in others:
            o_skills = _tags(o.get("skill_tags"))
            fill = o_skills & gap if gap else set()
            shared = o_skills & my_skills
            interests_hit = _tags(o.get("interest_tags")) & my_interests
            score = len(fill) * 3 + len(interests_hit) * 2 + len(shared)
            if score <= 0:
                continue
            persona_txt = ""
            if o.get("profile_public") and o.get("persona"):
                p = o["persona"]
                p = p if isinstance(p, dict) else json.loads(p)
                persona_txt = "；".join(
                    f"{k}：{v}" for k, v in p.items() if v and k in ("traits", "strengths")
                )[:120]
            why = []
            if fill:
                why.append(f"TA 的 {('、'.join(sorted(fill)))} 正好补你的缺口")
            if interests_hit:
                why.append(f"同频兴趣：{'、'.join(sorted(interests_hit))[:30]}")
            if not why and shared:
                why.append(f"技能相近（{('、'.join(sorted(shared)))[:30]}）可协作")
            cands.append(
                {
                    "nickname": o.get("nickname"),
                    "grade": o.get("grade"),
                    "major": o.get("major"),
                    "skills": sorted(o_skills)[:6],
                    "persona_public": persona_txt,
                    "why": "；".join(why),
                    "score": score,
                }
            )
        cands.sort(key=lambda c: -c["score"])

        # 互补项目对（我拥有的项目 x 他人项目）
        proj_pairs = []
        if my_projects:
            all_projects = rows_of(
                client.table("fs_projects")
                .select("id, title, owner_id, required_skills, domain_tags, stage")
                .neq("owner_id", uid)
                .execute()
            )
            for mp in my_projects:
                for op in all_projects[:80]:
                    dom = _tags(mp.get("domain_tags")) & _tags(op.get("domain_tags"))
                    if not dom:
                        continue
                    a, b = _tags(mp.get("required_skills")), _tags(op.get("required_skills"))
                    if a and a == b:
                        continue
                    proj_pairs.append(
                        {
                            "my_project": mp.get("title"),
                            "partner_project": op.get("title"),
                            "partner_project_id": op.get("id"),
                            "shared_domains": sorted(dom)[:2],
                            "hint": "领域同频、技能侧重不同，可联合推进或共享资源",
                        }
                    )
        return json.dumps(
            {
                "success": True,
                "action": "match_seed_partners",
                "my_skills": sorted(my_skills),
                "my_gaps": sorted(gap)[:6],
                "partner_candidates": cands[:4],
                "project_pairs": proj_pairs[:3],
                "hint": "请向用户解释互补点，征得同意后用 send_message 给对方留言牵线（说明你是谁、为何找TA、期望的协作方式）",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return err_str(f"匹配失败：{e}")


@tool
def team_overview(nickname: str) -> str:
    """团队总览：查看我加入/带领的团队（含协作空间状态）与我作为队长收到的待审批入队申请。
    用户问"我的队伍/谁申请了加入/组队进展"时调用。申请通过请引导用户在网页组队空间操作（或告知申请者昵称）。

    Args:
        nickname: 当前用户昵称
    """
    try:
        client = get_supabase_client()
        uid = require_user_id(nickname)
        my_members = rows_of(
            client.table("fs_team_members")
            .select("team_id, role, status, applied_at")
            .eq("user_id", uid)
            .execute()
        )
        team_ids = [m["team_id"] for m in my_members]
        teams_map = {}
        if team_ids:
            rows = rows_of(
                client.table("fs_teams")
                .select("id, name, description, leader_id, project_id, status, created_at")
                .in_("id", team_ids)
                .execute()
            )
            teams_map = {t["id"]: t for t in rows}
        leader_name = {}
        if teams_map:
            lids = {t["leader_id"] for t in teams_map.values()}
            if lids:
                for u in rows_of(
                    client.table("fs_users").select("id, nickname").in_("id", list(lids)).execute()
                ):
                    leader_name[u["id"]] = u["nickname"]

        my_teams = []
        for m in my_members:
            t = teams_map.get(m["team_id"])
            if not t:
                continue
            my_teams.append(
                {
                    "team_id": t["id"],
                    "name": t.get("name"),
                    "role": "队长" if m["role"] == "leader" else "成员",
                    "my_status": m["status"],
                    "team_status": t.get("status"),
                    "leader": leader_name.get(t.get("leader_id")),
                    "description": (t.get("description") or "")[:80],
                }
            )

        pending_apps = []
        lead_team_ids = [m["team_id"] for m in my_members if m["role"] == "leader"]
        if lead_team_ids:
            apps = rows_of(
                client.table("fs_team_members")
                .select("team_id, user_id, status, note, applied_at")
                .in_("team_id", lead_team_ids)
                .eq("status", "pending")
                .execute()
            )
            if apps:
                uids = list({a["user_id"] for a in apps})
                umap = {
                    u["id"]: u
                    for u in rows_of(
                        client.table("fs_users")
                        .select("id, nickname, grade, major, skill_tags, persona, profile_public")
                        .in_("id", uids)
                        .execute()
                    )
                }
                for a in apps:
                    u = umap.get(a["user_id"], {})
                    persona_txt = ""
                    if u.get("profile_public") and u.get("persona"):
                        p = u["persona"]
                        p = p if isinstance(p, dict) else json.loads(p)
                        persona_txt = "；".join(
                            f"{k}：{v}" for k, v in p.items() if v and k in ("traits", "strengths")
                        )[:100]
                    t = teams_map.get(a["team_id"], {})
                    pending_apps.append(
                        {
                            "team_id": a["team_id"],
                            "team_name": t.get("name"),
                            "applicant": u.get("nickname"),
                            "grade": u.get("grade"),
                            "major": u.get("major"),
                            "skills": (u.get("skill_tags") or [])[:6],
                            "persona_public": persona_txt,
                            "note": (a.get("note") or "")[:100],
                        }
                    )
        return json.dumps(
            {
                "success": True,
                "action": "team_overview",
                "my_teams": my_teams,
                "pending_applications": pending_apps,
                "hint": "待审批申请请在网页「组队空间」中通过/婉拒（会自动给申请者留言通知）",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return err_str(f"团队查询失败：{e}")

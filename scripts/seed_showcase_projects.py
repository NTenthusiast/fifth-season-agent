#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为演示库补充多领域项目种子（幂等、只增不删）。

在 Coze 项目终端中执行：
    python scripts/seed_showcase_projects.py

脚本会复用平台注入的 Supabase 凭据；以项目标题判重，不覆盖真实用户数据。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from storage.database.supabase_client import get_supabase_client  # noqa: E402


SEEDS = [
    ("校园夜归安全地图", "整理夜间照明、保卫点位与安全路线，已有两次实地踏勘记录。", ["校园安全", "地图"], ["实地调研", "数据整理", "前端开发"], "winter"),
    ("朋辈情绪急救手册", "邀请心理专业同学与辅导员共创可执行的同伴支持指南。", ["心理健康", "朋辈互助"], ["心理学", "内容编辑", "访谈"], "summer"),
    ("毕业季旧物循环站", "连接毕业生与新生，把教材、小家电和生活用品重新流转起来。", ["环保", "旧物循环"], ["活动运营", "物资管理", "视觉设计"], "winter"),
    ("校园流浪动物健康档案", "为校内流浪动物建立绝育、免疫、领养与志愿喂养记录。", ["动物保护", "志愿服务"], ["动物护理", "摄影", "数据管理"], "autumn"),
    ("课程经验接力库", "沉淀选课建议、学习路径与复习资料，让低年级少走弯路。", ["学习支持", "知识共享"], ["内容审核", "产品设计", "后端开发"], "spring"),
    ("无障碍教室巡检计划", "记录教学楼坡道、电梯、盲道与无障碍卫生间的真实可用性。", ["无障碍", "校园服务"], ["无障碍评估", "实地调研", "数据可视化"], "winter"),
    ("南大记忆口述史", "采访退休教师、校友与老员工，保存正在消失的校园记忆。", ["校史", "口述历史"], ["采访", "摄影", "音视频剪辑"], "summer"),
    ("实验室器材共享清单", "让闲置但可借用的传感器、开发板与测量工具被跨院系发现。", ["资源共享", "科研服务"], ["信息整理", "后端开发", "运营协调"], "spring"),
    ("新生防骗情景课", "把常见电信诈骗、兼职陷阱做成可互动的入学教育案例。", ["校园安全", "新生服务"], ["脚本创作", "交互设计", "宣讲"], "autumn"),
    ("校园低碳饮食指南", "记录食堂低碳菜品与剩餐情况，发起一周友好饮食挑战。", ["低碳", "饮食"], ["数据采集", "营养知识", "视觉设计"], "summer"),
    ("跨文化搭子计划", "为留学生与本地同学设计低压力、可持续的语言文化交流活动。", ["国际交流", "朋辈互助"], ["英语", "活动策划", "社群运营"], "spring"),
    ("女性友好卫生用品互助盒", "在教学楼建立可补充、可追踪的应急卫生用品互助点。", ["女性友好", "校园互助"], ["点位协调", "物资运营", "视觉设计"], "winter"),
    ("校园自然观察图鉴", "记录校园植物、鸟类与季节变化，形成开放的自然教育地图。", ["自然教育", "校园文化"], ["生物识别", "摄影", "科普写作"], "summer"),
    ("社团换届资料急救", "帮助社团把账号、物资、流程与合作方整理成标准交接包。", ["社团治理", "项目传承"], ["信息架构", "文档写作", "组织协调"], "autumn"),
    ("第一份实习互助工坊", "由高年级同学带领完成岗位探索、简历互评与模拟面试。", ["职业发展", "朋辈互助"], ["职业规划", "内容运营", "活动主持"], "spring"),
    ("夜跑友好路线", "结合照明、路面、人流与补给点，设计安全的校园夜跑路线。", ["运动健康", "校园地图"], ["跑步", "实地调研", "地图设计"], "winter"),
    ("方言里的南京", "采集同学与居民口述中的南京方言词汇，制作声音小词典。", ["地方文化", "声音档案"], ["语言学", "录音", "网页开发"], "spring"),
    ("闲置空间一小时", "盘点教学楼可临时使用的角落，为自习、小组讨论建立时段地图。", ["空间改造", "学习支持"], ["空间调研", "产品设计", "前端开发"], "summer"),
    ("食堂过敏原标注倡议", "调研常见过敏原信息缺口，与食堂共创清晰的菜品标识。", ["食品安全", "校园服务"], ["问卷调研", "营养知识", "沟通协调"], "winter"),
    ("急救设备与志愿者地图", "汇总 AED 点位与持证志愿者，形成校园应急响应指引。", ["急救", "校园安全"], ["急救知识", "地图开发", "组织协调"], "autumn"),
    ("科研失败经验匿名库", "以脱敏方式记录实验失败原因与排查过程，减少重复踩坑。", ["科研互助", "知识共享"], ["科研经验", "匿名化", "产品设计"], "spring"),
    ("校园微纪录片接力", "每届拍摄一集真实校园人物故事，并把素材与授权完整交接。", ["影像", "校园文化"], ["摄影", "剪辑", "采访"], "winter"),
    ("宿舍维修透明看板", "收集高频维修问题与处理时长，帮助同学了解进度并减少重复报修。", ["宿舍服务", "数据透明"], ["数据分析", "前端开发", "用户调研"], "summer"),
    ("考试周互助自习搭子", "按课程、时间和学习目标匹配自习伙伴，并沉淀互助笔记。", ["学习支持", "同伴互助"], ["社群运营", "产品设计", "学习规划"], "spring"),
]


def one(rows):
    data = getattr(rows, "data", None) or []
    return data[0] if data else None


def main() -> None:
    client = get_supabase_client()
    nickname = "第五季示范库"
    user = one(client.table("fs_users").select("id").eq("nickname", nickname).limit(1).execute())
    if user is None:
        user = one(client.table("fs_users").insert({
            "nickname": nickname,
            "grade": "公共项目档案",
            "major": "校园共创",
            "skill_tags": ["项目记录", "交接整理"],
            "interest_tags": ["校园服务", "公共记忆"],
            "bio": "用于承载公开演示种子，不代表真实学生。",
        }).execute())
    user_id = int(user["id"])

    existing = client.table("fs_projects").select("title").execute().data or []
    existing_titles = {str(row.get("title")) for row in existing}
    created = 0
    now = datetime.now(timezone.utc)

    for index, (title, summary, domains, skills, stage) in enumerate(SEEDS):
        if title in existing_titles:
            continue
        payload = {
            "title": title,
            "summary": summary,
            "domain_tags": domains,
            "required_skills": skills,
            "stage": stage,
            "founder_id": user_id,
            "owner_id": user_id,
        }
        if stage == "winter":
            payload["hibernate_reason"] = "原团队成员毕业或学期结束，资料已整理，等待接棒"
            payload["hibernate_at"] = (now - timedelta(days=90 + index * 17)).isoformat()
        project = one(client.table("fs_projects").insert(payload).execute())
        project_id = int(project["id"])
        client.table("fs_project_members").insert({
            "project_id": project_id, "user_id": user_id, "role": "档案整理人"
        }).execute()
        client.table("fs_project_updates").insert({
            "project_id": project_id,
            "author_id": user_id,
            "content": "示范种子已完成基础调研与资料建档，后续需要真实学生团队认领并继续验证。",
            "stage": stage,
        }).execute()
        if stage == "winter":
            client.table("fs_handover_packages").insert({
                "project_id": project_id,
                "achievements": json.dumps(["完成问题定义与一轮基础调研"], ensure_ascii=False),
                "experience": json.dumps(["先从一个校区或一栋楼做小范围验证"], ensure_ascii=False),
                "pitfalls": json.dumps(["需提前确认场地、隐私与相关部门协作边界"], ensure_ascii=False),
                "remaining_issues": json.dumps(["招募真实接棒团队并补充用户访谈"], ensure_ascii=False),
                "reusable_resources": json.dumps(["项目种子卡、调研框架与首轮问题清单"], ensure_ascii=False),
            }).execute()
        created += 1

    total = len(client.table("fs_projects").select("id").execute().data or [])
    print(json.dumps({"新增项目": created, "项目总数": total, "判重方式": "标题"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

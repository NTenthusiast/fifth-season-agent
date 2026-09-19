#!/usr/bin/env python3
"""六维可解释匹配纯函数冒烟测试；无需数据库。

维度权重：技能互补 40 / 兴趣与议题 25 / 年级阶梯 10 / 传承准备度 10 /
社交邻近 8 / 时间投入 7；缺信息维度不计入总分并显式披露。
"""

from pure_function_loader import load


score_project_match, = load("score_project_match")


def test_match_uses_only_known_evidence():
    profile = {
        "skill_tags": ["前端开发", "摄影"],
        "interest_tags": ["无障碍", "校园服务"],
        "bio": "每周可投入 4 小时",
    }
    project = {
        "required_skills": ["前端开发", "实地调研"],
        "domain_tags": ["无障碍", "校园服务"],
        "stage": "winter",
    }
    result = score_project_match(profile, project)
    # 技能 40*(1/2)=20 兴趣 25*(2/2)=25 准备度 10 时间 7 邻近 min(8, 2*4)=8 = 70/90
    assert result["score"] == round(70 / 90 * 100), result["score"]
    assert result["evidence"]["技能命中"] == ["前端开发"]
    assert result["evidence"]["待补能力"] == ["实地调研"]
    assert result["uncertainty"] is None or "年级" in result["uncertainty"]


def test_unknown_time_is_disclosed_and_not_fabricated():
    result = score_project_match(
        {"skill_tags": ["摄影"], "interest_tags": ["校史"], "bio": "周末偶尔参加"},
        {"required_skills": ["摄影"], "domain_tags": ["校史"], "stage": "winter"},
    )
    assert result["dimensions"]["时间投入"] is None
    assert result["dimensions"]["年级阶梯"] is None
    assert result["dimensions"]["社交邻近"] is not None  # 兴趣与领域重合可推断
    assert "未计入总分" in result["uncertainty"]
    assert "三步确认" in result["decision_boundary"]


def test_grade_ladder_rewards_underclassmen():
    """年级阶梯：低年级接棒长期项目加分，毕业班降档并提示风险。"""
    senior = score_project_match(
        {"skill_tags": ["摄影"], "interest_tags": ["校史"], "grade": "大四", "bio": "每周 3 小时"},
        {"required_skills": ["摄影"], "domain_tags": ["校史"], "stage": "winter"},
    )
    junior = score_project_match(
        {"skill_tags": ["摄影"], "interest_tags": ["校史"], "grade": "大二", "bio": "每周 3 小时"},
        {"required_skills": ["摄影"], "domain_tags": ["校史"], "stage": "winter"},
    )
    assert junior["dimensions"]["年级阶梯"] > senior["dimensions"]["年级阶梯"]
    assert senior["dimensions"]["年级阶梯"] == 3
    assert "临近毕业" in senior["uncertainty"]
    assert junior["uncertainty"] is None


def test_confirmation_flow_present():
    """匹配结果必须携带三步确认流程，杜绝一步到位式自动交接。"""
    result = score_project_match(
        {"skill_tags": ["前端开发"], "interest_tags": ["无障碍"], "grade": "大一"},
        {"required_skills": ["前端开发"], "domain_tags": ["无障碍"], "stage": "winter"},
    )
    assert len(result["confirmation_flow"]) == 3
    assert "原负责人" in result["confirmation_flow"][1]
    assert "正式唤醒" in result["confirmation_flow"][2]


if __name__ == "__main__":
    test_match_uses_only_known_evidence()
    test_unknown_time_is_disclosed_and_not_fabricated()
    test_grade_ladder_rewards_underclassmen()
    test_confirmation_flow_present()
    print("explainable match tests passed (6-dimension)")

#!/usr/bin/env python3
"""交接准备度纯函数测试；无需数据库。"""

from pure_function_loader import load


assess_transfer_readiness, = load("assess_transfer_readiness")


def _package(resources):
    return {
        "achievements": ["已完成需求调研"],
        "experience": ["先做小范围验证"],
        "pitfalls": ["避免无授权传播"],
        "remaining_issues": ["补齐第二轮测试"],
        "reusable_resources": resources,
    }


def test_complete_package_is_relay_ready():
    result = assess_transfer_readiness(
        _package([
            "调研模板",
            "【授权范围】仅校内公益使用",
            "【资源有效期】长期有效",
            "【原团队权益】保留署名，重大改编需确认",
        ]),
        [{"id": 1}],
    )
    assert result["score"] == 100
    assert result["level"] == "可接棒"
    assert result["blockers"] == []


def test_missing_governance_is_blocked():
    result = assess_transfer_readiness(_package(["调研模板"]), [{"id": 1}])
    assert result["score"] == 70
    assert result["level"] == "需补充"
    assert len(result["blockers"]) == 3


if __name__ == "__main__":
    for expiry in ["2000-01-01", "", "无效日期"]:
        result = assess_transfer_readiness(_package([
            "【授权范围】校内使用", "【资源有效期】" + expiry,
            "【原团队权益】保留署名",
        ]), [{"id": 1}])
        assert result["score"] < 100
        assert not result["checks"]["validity_declared"]
    test_complete_package_is_relay_ready()
    test_missing_governance_is_blocked()
    print("transfer readiness tests passed")

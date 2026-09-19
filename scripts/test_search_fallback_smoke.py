"""无数据库依赖地冒烟测试项目检索的同义主题评分逻辑。"""

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "src" / "tools" / "project_tools.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
selected = [
    node
    for node in tree.body
    if (
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_TOPIC_GROUPS" for target in node.targets)
    )
    or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    and node.name in {"_query_terms", "_related_score"}
]
module = ast.Module(
    body=[ast.Import(names=[ast.alias(name="re")]), ast.ImportFrom(module="typing", names=[ast.alias(name="Optional")], level=0), *selected],
    type_ignores=[],
)
namespace: dict = {}
exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

terms = namespace["_query_terms"]("想做旧衣回收", "环保")
project = {
    "title": "校园旧物循环站",
    "summary": "旧衣捐赠与低碳行动",
    "domain_tags": ["可持续"],
    "required_skills": ["运营"],
}
score, hits = namespace["_related_score"](project, terms)
assert score > 0, (score, hits)
assert {"回收", "环保", "可持续"}.intersection(terms)
print(f"检索兜底冒烟测试通过：score={score}, hits={hits}")

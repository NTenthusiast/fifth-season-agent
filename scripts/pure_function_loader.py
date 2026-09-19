"""从 project_tools.py 隔离加载纯函数，避免测试依赖平台 SDK。"""

import ast
import json
import re
from datetime import date
from pathlib import Path
from typing import Optional


def _parse_json_list(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else [str(raw)]
    except (json.JSONDecodeError, TypeError):
        return [str(raw)]


def load(*names):
    source_path = Path(__file__).resolve().parents[1] / "src" / "tools" / "project_tools.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    # 携带被提取函数引用的模块级赋值常量（如 _GRADE_LADDER）
    assign_names = set()
    for node in selected:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                assign_names.add(sub.id)
    consts = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in assign_names for t in node.targets)
    ]
    selected = consts + selected
    namespace = {"Optional": Optional, "parse_json_list": _parse_json_list, "re": re, "date": date}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source_path), "exec"), namespace)
    return [namespace[name] for name in names]

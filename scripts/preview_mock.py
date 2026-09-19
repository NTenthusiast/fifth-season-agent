#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地预览服务器（开发工具，非产品代码）。

用途：在不连接数据库与模型网关的前提下，把 assets/web 的前端完整跑起来，
用于验收页面改动——包括移动端导航、hero 标题自适应、以及新增的「工具执行进度」
SSE 事件。所有数据均为演示用的假数据，不写入任何数据库。

启动：
    python scripts/preview_mock.py            # 默认 http://localhost:8000
    python scripts/preview_mock.py -p 9000

注意：
- 仅使用 Python 标准库，无需安装任何第三方依赖。
- 本文件不参与线上部署；如需精简参赛包，可整份删除。
"""

import argparse
import json
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

WEB_DIR = Path(__file__).resolve().parent.parent / "assets" / "web"

# ---------------------------------------------------------------------------
# 演示数据（全部为假数据，仅用于把页面填满）
# ---------------------------------------------------------------------------
STATS = {"users": 30, "projects": 19, "awakened": 2}

SKILLS = {
    "users": 30, "projects": 19,
    "skills": [
        {"skill": "实地调研", "supply": 3, "demand": 9, "gap": 6, "status": "稀缺"},
        {"skill": "视觉设计", "supply": 5, "demand": 7, "gap": 2, "status": "稀缺"},
        {"skill": "无障碍评估", "supply": 1, "demand": 4, "gap": 3, "status": "稀缺"},
        {"skill": "前端开发", "supply": 8, "demand": 6, "gap": -2, "status": "富余"},
        {"skill": "文案写作", "supply": 9, "demand": 4, "gap": -5, "status": "富余"},
    ],
}

DORMANT = {"dormant": [
    {"id": 3, "title": "为视障同学制作校园无障碍地图", "summary": "标注校内无障碍通道与设施，已完成两栋教学楼的测绘与调研。",
     "hibernate_reason": "发起人毕业", "dormant_days": 1095, "votes": 12, "founder_nickname": "陈屿",
     "domain_tags": ["无障碍", "校园服务"], "required_skills": ["实地调研", "前端开发"]},
    {"id": 7, "title": "校园旧物循环站", "summary": "毕业季物资回收与流转，已谈妥两个投放点。",
     "hibernate_reason": "换届断档", "dormant_days": 214, "votes": 8, "founder_nickname": "林一舟",
     "domain_tags": ["环保", "公益"], "required_skills": ["活动运营", "视觉设计"]},
]}

STORIES = {"stories": [
    {"id": 1, "project_id": 3, "project_title": "校园手绘地图·向云端", "founder_nickname": "苏晓",
     "successor_nickname": "周珩", "match_reason": "接棒者具备手绘与排版能力，与项目缺口吻合",
     "story_text": "「校园手绘地图·向云端」由 苏晓 发起，在校园记忆库中沉睡了 412 天，被 周珩 唤醒接棒——第五季，让未完成的美好重新发生。",
     "highlights": ["完成校本部全部 6 个片区的实地踏勘", "沉淀 3 套可复用的手绘风格模板"],
     "period_days": 412, "is_featured": True, "likes": 27},
]}

LEADERBOARD = {"leaderboard": [
    {"rank": 1, "user_id": 4, "nickname": "周珩", "grade": "2023级", "major": "建筑学", "points": 95},
    {"rank": 2, "user_id": 9, "nickname": "苏晓", "grade": "2022级", "major": "新闻传播", "points": 80},
    {"rank": 3, "user_id": 15, "nickname": "林一舟", "grade": "2024级", "major": "软件工程", "points": 45},
]}

# 脚本化的对话：每轮演示「工具进度 → 正文流式」，用于验收 SSE 工具事件
SCRIPT = [
    {
        "tools": ["get_user_profile"],
        "reply": (
            "记忆库里还没有你的档案。先花一分钟建一份——我需要三样东西：\n\n"
            "- **年级与专业**\n"
            "- **擅长技能**（越具体越好，比如「前端开发」而不是「会写代码」）\n"
            "- **兴趣方向**（比如「无障碍」「环保」「校园文创」）\n\n"
            "档案越完整，后面给你匹配项目时越准。"
        ),
    },
    {
        "tools": ["upsert_user_profile", "search_projects"],
        "reply": (
            "【种子卡 #3】为视障同学制作校园无障碍地图\n\n"
            "- 阶段：冬·蛰伏（已休眠 1095 天）\n"
            "- 领域：无障碍 / 校园服务\n"
            "- 所需能力：实地调研 / 前端开发\n"
            "- 发起人：陈屿\n\n"
            "**这颗种子的故事**\n"
            "三年前由建筑学院的同学发起，完成了两栋教学楼的完整测绘与调研报告。"
            "发起人毕业那年，剩下的五栋楼没人接手，项目就此停住。\n\n"
            "**为什么是你**\n"
            "你的前端能力正好接上它缺的那一环——前任已经把调研方法和原型留下来了，"
            "你不需要从零开始。\n\n"
            "**接手第一步**\n"
            "先花一周读完旧团队的调研与原型，再决定要不要碰剩下的五栋楼。"
            "有两件事你该提前知道：物业协调需要提前两周预约；"
            "电梯盲区的测量需要两人配合。\n\n"
            "要我调出完整交接包给你看吗？"
        ),
    },
    {
        "tools": ["get_project_detail", "save_handover_package"],
        "reply": (
            "完整交接包已经调出，并按五件套整理好了：\n\n"
            "1. **已有成果**：两栋教学楼无障碍测绘表、访谈纪要 18 份、可交互地图原型 1 套\n"
            "2. **执行经验**：先联系物业确认路线，再邀请视障同学进行实地验证\n"
            "3. **踩过的坑**：只按建筑图纸标注会遗漏临时障碍，必须现场复核\n"
            "4. **遗留问题**：其余五栋楼待测；电梯盲区数据尚未补齐\n"
            "5. **可复用资源**：问卷模板、测绘规范、物业联系人与原型源文件\n\n"
            "这不是一份只有结果的总结，而是一张可以直接继续执行的地图。"
            "如果你确认接棒，我会更新负责人并留下完整传承记录。"
        ),
    },
    {
        "tools": ["awaken_project", "save_match_log"],
        "reply": (
            "✨ **第五季已经发生：项目 #3 唤醒成功。**\n\n"
            "- 新负责人：小林\n"
            "- 项目阶段：第五季·唤醒\n"
            "- 匹配理由：前端开发能力与地图原型缺口吻合\n"
            "- 第一周行动：阅读旧团队材料，并预约一次物业沟通\n\n"
            "原团队留下的成果、踩坑和资源都没有丢。"
            "这次接棒已经写入传承记录，故事卡与「第五季唤醒者」成就也会同步点亮。"
        ),
    },
]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 静音访问日志
        pass

    # ---------------- 工具方法 ----------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, ctype: str):
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _sse(self, payload):
        frame = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        self.wfile.write(frame)
        self.wfile.flush()

    # ---------------- 路由 ----------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/api/health":
            self._send_json({"status": "ok", "agent_ready": True})
        elif path == "/api/stats":
            self._send_json(STATS)
        elif path == "/api/skills":
            self._send_json(SKILLS)
        elif path == "/api/dormant":
            self._send_json(DORMANT)
        elif path == "/api/stories":
            self._send_json(STORIES)
        elif path == "/api/leaderboard":
            self._send_json(LEADERBOARD)
        elif path.startswith("/static/"):
            rel = path[len("/static/"):]
            ctype = {
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".png": "image/png",
                ".svg": "image/svg+xml",
            }.get(Path(rel).suffix, "application/octet-stream")
            self._send_file(WEB_DIR / rel, ctype)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}

        if path == "/api/chat":
            self._chat(body)
        elif path == "/api/votes":
            self._send_json({"action": "voted", "project_id": body.get("project_id"),
                             "title": "演示项目", "votes": random.randint(3, 20)})
        elif path.startswith("/api/stories/") and path.endswith("/like"):
            self._send_json({"likes": random.randint(5, 40)})
        else:
            self._send_json({"error": "not found"}, 404)

    # ---------------- SSE 对话 ----------------
    def _chat(self, body):
        message = (body or {}).get("message") or ""
        # 演示按用户意图路由，避免刷新或并发请求令固定轮次错位。
        if "确认接棒" in message or "唤醒这个项目" in message:
            step = 3
        elif "交接包" in message:
            step = 2
        elif any(word in message for word in ("大二", "建档", "前端开发", "无障碍")):
            step = 1
        else:
            step = 0
        turn = SCRIPT[step]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True  # SSE 结束后关闭连接，避免 HTTP/1.1 长连接挂住

        try:
            # 1) 工具执行进度（本轮新增的能力）
            for name in turn["tools"]:
                self._sse({"type": "tool", "label": _tool_label(name)})
                time.sleep(0.7)

            # 2) 正文按小块流式吐出，模拟真实打字节奏
            text = turn["reply"]
            for i in range(0, len(text), 6):
                self._sse({"type": "delta", "text": text[i:i + 6]})
                time.sleep(0.012)

            self._sse({"type": "done"})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # 客户端主动断开（如 curl 接 head），属正常现象，不打错误日志


_LABELS = {
    "get_user_profile": "正在查阅你的档案…",
    "upsert_user_profile": "正在建立你的档案…",
    "search_projects": "正在检索校园项目库…",
    "get_project_detail": "正在调取项目完整资料…",
    "save_handover_package": "正在整理交接包五件套…",
    "awaken_project": "正在唤醒休眠种子…",
    "save_match_log": "正在保存匹配与传承记录…",
}


def _tool_label(name: str) -> str:
    return _LABELS.get(name, "正在处理…")


def main():
    ap = argparse.ArgumentParser(description="第五季 前端本地预览（假数据，无需依赖）")
    ap.add_argument("-p", "--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    if not (WEB_DIR / "index.html").is_file():
        raise SystemExit(f"未找到前端目录：{WEB_DIR}")

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv._turn = 0
    print(f"前端预览已启动： http://{args.host}:{args.port}/")
    print(f"静态目录： {WEB_DIR}")
    print("提示：对话内容为脚本化的演示文本，不连接数据库与模型。Ctrl+C 退出。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()

"""生成参赛演示视频所需的 16:9 画面与 ffmpeg 合成命令。"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "video_assets"
SLIDES = ASSETS / "slides"
SCREEN_DIR = ASSETS / "screens"
NARRATION = ASSETS / "narration" / "旁白.mp3"
SUBTITLES = ASSETS / "narration" / "旁白.srt"
OUTPUT = ROOT / "docs" / "第五个季节-第五季·续种.mp4"
FFMPEG = ROOT / ".vendor" / "imageio_ffmpeg" / "binaries" / "ffmpeg-win-x86_64-v7.1.exe"

W, H = 1920, 1080
PURPLE = "#6650C8"
INK = "#182234"
MUTED = "#60708A"
FONT_REG = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold and FONT_BOLD.exists() else FONT_REG), size)


def gradient() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    px = image.load()
    for y in range(H):
        for x in range(W):
            a = x / W
            b = y / H
            r = int(246 + 6 * a + 2 * b)
            g = int(249 - 2 * a + 1 * b)
            bl = int(252 + 2 * a - 4 * b)
            px[x, y] = (min(r, 255), min(g, 255), min(bl, 255))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((110, 80, 980, 950), fill=(151, 215, 190, 35))
    gd.ellipse((1050, 20, 2020, 920), fill=(207, 168, 238, 35))
    gd.ellipse((650, 530, 1500, 1300), fill=(250, 190, 137, 24))
    return Image.alpha_composite(image.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(90)))


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
         color: str = INK, bold: bool = False, anchor: str | None = None) -> None:
    draw.text(xy, value, font=font(size, bold), fill=color, anchor=anchor)


def footer(draw: ImageDraw.ImageDraw, index: int, label: str) -> None:
    y = H - 76
    draw.line((120, y, W - 120, y), fill="#D9DDED", width=2)
    text(draw, (120, y + 22), f"第五季·续种  ·  {label}", 22, MUTED)
    text(draw, (W - 120, y + 22), f"{index:02d} / 08", 22, PURPLE, True, "ra")


def draw_brand_logo(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float = 3.2) -> None:
    """按网页 SVG 的贝塞尔轮廓绘制五瓣嫩芽标志。"""
    cx, cy = center
    base = []
    curves = [
        ((0, -12.5), (6.6, -23.5), (7.2, -35.5), (0, -43)),
        ((0, -43), (-7.2, -35.5), (-6.6, -23.5), (0, -12.5)),
    ]
    for p0, p1, p2, p3 in curves:
        for step in range(18):
            t = step / 17
            u = 1 - t
            x = u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0]
            y = u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]
            base.append((x * scale, y * scale))
    colors = ["#4e9e6b", "#dfa12e", "#d97444", "#5c86c4", "#7b5cd6"]
    for i, color in enumerate(colors):
        angle = math.radians(i * 72)
        points = [
            (cx + x*math.cos(angle) - y*math.sin(angle), cy + x*math.sin(angle) + y*math.cos(angle))
            for x, y in base
        ]
        draw.polygon(points, fill=color)
    r = 13 * scale
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill="#5b3fb8", outline="#b9ace8", width=3)
    draw.line((cx, cy+22, cx-3, cy-3, cx-16, cy-18), fill="white", width=5)
    draw.line((cx, cy+22, cx+3, cy+4, cx+17, cy-14), fill="white", width=5)
    draw.ellipse((cx-28, cy-30, cx-10, cy-14), fill="white")
    draw.ellipse((cx+10, cy-27, cx+29, cy-11), fill="white")


def rounded_panel(canvas: Image.Image, box: tuple[int, int, int, int], radius: int = 34) -> ImageDraw.ImageDraw:
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = box
    sd.rounded_rectangle((x1 + 8, y1 + 14, x2 + 8, y2 + 14), radius, fill=(70, 62, 104, 35))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(box, radius, fill=(255, 255, 255, 235), outline="#E1E3EF", width=2)
    return d


def fit_screen(canvas: Image.Image, source: Path, box: tuple[int, int, int, int]) -> None:
    shot = Image.open(source).convert("RGB")
    x1, y1, x2, y2 = box
    target_w, target_h = x2 - x1, y2 - y1
    scale = min(target_w / shot.width, target_h / shot.height)
    resized = shot.resize((int(shot.width * scale), int(shot.height * scale)), Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", (target_w, target_h), (255, 255, 255, 0))
    frame.alpha_composite(resized.convert("RGBA"), ((target_w - resized.width) // 2, (target_h - resized.height) // 2))
    mask = Image.new("L", (target_w, target_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, target_w, target_h), 28, fill=255)
    frame.putalpha(mask)
    canvas.alpha_composite(frame, (x1, y1))


def make_slides() -> None:
    SLIDES.mkdir(parents=True, exist_ok=True)

    # 1 封面
    c = gradient(); d = ImageDraw.Draw(c)
    draw_brand_logo(d, (960, 252), 3.2)
    text(d, (960, 454), "第五季·续种", 104, INK, True, "mm")
    text(d, (960, 570), "校园未竟梦想的 AI 传承智能体", 42, PURPLE, False, "mm")
    text(d, (960, 692), "让未完成，不再等于失败", 34, MUTED, False, "mm")
    footer(d, 1, "问题与愿景")
    c.convert("RGB").save(SLIDES / "01.png", quality=95)

    # 2 痛点
    c = gradient(); d = ImageDraw.Draw(c)
    text(d, (120, 110), "项目停下了，经验也随人离场", 64, INK, True)
    text(d, (122, 198), "毕业、换届、时间冲突，让下一届一次次从零开始", 30, MUTED)
    cards = [("01", "资料散落", "文件在个人电脑，渠道留在私人微信"),
             ("02", "经验沉默", "踩过的坑和关键判断没有被记录"),
             ("03", "交接断裂", "想接棒的人找不到项目，也找不到前人")]
    for i, (no, title, desc) in enumerate(cards):
        x1 = 120 + i * 575
        rounded_panel(c, (x1, 330, x1 + 520, 790))
        text(d, (x1 + 48, 382), no, 34, PURPLE, True)
        text(d, (x1 + 48, 500), title, 48, INK, True)
        text(d, (x1 + 48, 600), desc, 27, MUTED)
    footer(d, 2, "用户痛点")
    c.convert("RGB").save(SLIDES / "02.png", quality=95)

    # 3 产品界面
    c = gradient(); d = ImageDraw.Draw(c)
    text(d, (120, 84), "一个入口，接住项目的完整生命周期", 58, INK, True)
    text(d, (122, 160), "春日萌芽 · 夏日生长 · 秋日沉淀 · 冬日休眠 · 第五季唤醒", 28, PURPLE)
    rounded_panel(c, (120, 230, 1800, 910), 32)
    fit_screen(c, SCREEN_DIR / "01-intro.png", (142, 252, 1778, 888))
    footer(d, 3, "产品定位")
    c.convert("RGB").save(SLIDES / "03.png", quality=95)

    # 4 交互与检索
    c = gradient(); d = ImageDraw.Draw(c)
    text(d, (120, 84), "不让“没有相关项目”成为对话终点", 58, INK, True)
    text(d, (122, 160), "先从任务出发，再用三级检索退路给出下一步", 28, MUTED)
    rounded_panel(c, (120, 230, 1160, 900), 32)
    fit_screen(c, SCREEN_DIR / "02-chat.png", (142, 252, 1138, 878))
    steps = [("1", "精确匹配"), ("2", "同义主题扩展"), ("3", "探索推荐")]
    for i, (no, label) in enumerate(steps):
        y = 290 + i * 170
        d.ellipse((1260, y, 1330, y + 70), fill=PURPLE)
        text(d, (1295, y + 35), no, 28, "white", True, "mm")
        text(d, (1370, y + 35), label, 34, INK, True, "lm")
        if i < 2: d.line((1295, y + 82, 1295, y + 148), fill="#CFC7F0", width=5)
    text(d, (1260, 808), "诚实标注“相关方向”\n不把兜底冒充命中", 27, MUTED)
    footer(d, 4, "检索体验")
    c.convert("RGB").save(SLIDES / "04.png", quality=95)

    # 5 示范库
    c = gradient(); d = ImageDraw.Draw(c)
    text(d, (120, 100), "项目库，从“少量样例”扩展到多议题种子", 58, INK, True)
    text(d, (120, 178), "24 条幂等示范种子 · 14 类议题 · 覆盖五个阶段", 31, PURPLE, True)
    topics = ["公益", "环保", "心理", "设计", "技术", "无障碍", "文化", "学习", "就业", "运动", "动物", "国际", "校园服务", "社团"]
    for i, topic in enumerate(topics):
        row, col = divmod(i, 5)
        x, y = 120 + col * 338, 310 + row * 150
        d.rounded_rectangle((x, y, x + 290, y + 92), 46, fill="white", outline="#D8D4EC", width=2)
        text(d, (x + 145, y + 46), topic, 31, INK, True, "mm")
    text(d, (120, 825), "按标题判重 · 可重复执行 · 不删除、不覆盖真实用户数据", 29, MUTED)
    footer(d, 5, "项目库扩充")
    c.convert("RGB").save(SLIDES / "05.png", quality=95)

    # 6 传承闭环
    c = gradient(); d = ImageDraw.Draw(c)
    text(d, (120, 95), "真正的传承，是把“做过什么”变成“下一步怎么做”", 55, INK, True)
    flow = [("已有成果", "留下可复用产物"), ("执行经验", "保存关键判断"), ("踩过的坑", "避免重复失败"),
            ("遗留问题", "明确接手起点"), ("可用资源", "续上渠道与材料")]
    for i, (title, desc) in enumerate(flow):
        x = 95 + i * 360
        rounded_panel(c, (x, 360, x + 310, 670), 30)
        d.ellipse((x + 112, 285, x + 198, 371), fill=["#5CB57D", "#E5AC39", "#D8734E", "#6187CC", "#7B57D1"][i])
        text(d, (x + 155, 328), str(i + 1), 30, "white", True, "mm")
        text(d, (x + 155, 458), title, 34, INK, True, "mm")
        text(d, (x + 155, 550), desc, 24, MUTED, False, "mm")
        if i < 4: text(d, (x + 335, 510), "→", 42, PURPLE, True, "mm")
    text(d, (960, 785), "确认接棒后：负责人、阶段、传承记录、故事卡与成就同步更新", 30, PURPLE, True, "mm")
    footer(d, 6, "交接与唤醒")
    c.convert("RGB").save(SLIDES / "06.png", quality=95)

    # 7 技术方案
    c = gradient(); d = ImageDraw.Draw(c)
    text(d, (120, 90), "基于 Coze 的可执行智能体，而非概念原型", 58, INK, True)
    layers = [("交互层", "原生 HTML / CSS / JS · SSE 流式对话"),
              ("智能体层", "26 个工具 · 四季状态机 · 记忆保护"),
              ("模型层", "豆包模型 · 意图路由 · 结果诚实约束"),
              ("数据层", "Supabase PostgreSQL · 14 张业务表"),
              ("产物层", "交接包 · 海报 · 托付书 · 故事卡")]
    for i, (name, desc) in enumerate(layers):
        y = 245 + i * 135
        d.rounded_rectangle((180, y, 1740, y + 102), 26, fill="white", outline="#DDD9EF", width=2)
        d.rounded_rectangle((180, y, 455, y + 102), 26, fill=["#E7F5EC", "#EEE9FB", "#FFF3D8", "#E8F0FB", "#FCE9E2"][i])
        text(d, (318, y + 51), name, 30, PURPLE, True, "mm")
        text(d, (500, y + 51), desc, 29, INK, False, "lm")
    footer(d, 7, "技术实现")
    c.convert("RGB").save(SLIDES / "07.png", quality=95)

    # 8 结尾
    c = gradient(); d = ImageDraw.Draw(c)
    text(d, (960, 270), "未完成，不等于失败", 86, INK, True, "mm")
    text(d, (960, 410), "它只是正在等待下一双手", 46, PURPLE, False, "mm")
    text(d, (960, 610), "春日提出  ·  夏日行动  ·  秋日沉淀  ·  冬日守望", 31, MUTED, False, "mm")
    text(d, (960, 700), "待到第五季，让未完成的美好重新发生", 39, INK, True, "mm")
    footer(d, 8, "第五季·续种")
    c.convert("RGB").save(SLIDES / "08.png", quality=95)


def build_video() -> None:
    durations = [19.0, 19.0, 22.0, 24.0, 21.0, 20.0, 20.0, 15.3]
    args = [str(FFMPEG), "-y"]
    for i, duration in enumerate(durations, 1):
        args += ["-loop", "1", "-t", str(duration), "-i", str(SLIDES / f"{i:02d}.png")]
    args += ["-i", str(NARRATION)]
    filters = []
    for i in range(8):
        filters.append(f"[{i}:v]scale={W}:{H},format=yuv420p[v{i}]")
    current = "v0"
    elapsed = durations[0]
    for i in range(1, 8):
        offset = elapsed - i
        out = f"x{i}"
        filters.append(f"[{current}][v{i}]xfade=transition=fade:duration=1:offset={offset:.2f}[{out}]")
        current = out
        elapsed += durations[i]
    subtitle_path = str(SUBTITLES.relative_to(ROOT)).replace("\\", "/")
    filters.append(
        f"[{current}]subtitles='{subtitle_path}':force_style='FontName=Microsoft YaHei,FontSize=9,"
        "PrimaryColour=&H00342218,OutlineColour=&H00FFFFFF,BorderStyle=1,Outline=1.5,Shadow=0,"
        "Alignment=2,MarginV=28'[vout]"
    )
    args += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "8:a:0", "-shortest",
        "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
        str(OUTPUT),
    ]
    subprocess.run(args, cwd=ROOT, check=True)


if __name__ == "__main__":
    make_slides()
    build_video()
    print(OUTPUT)

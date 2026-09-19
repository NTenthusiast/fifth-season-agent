# -*- coding: utf-8 -*-
"""
南大真实档案项目入库（v6.1）
- fs_users 增加 contact 列（自愿留联系方式）
- 入库 3 个"档案级"南大真实项目（整理自公开报道，标注来源）+ 轻量交接包
- 案例库扩充 7 条南大真实案例
数据来源（已联网核实）:
  - 南京大学研究生支教团: 1999年首批、26届接力、6省10县32所中小学
  - 小百合BBS: 1997年建站、38万注册账户、2013校园文化十大品牌
  - 《蒋公的面子》: 2011年创作、62场+公演、一届届艺术硕士接力
"""
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from storage.database.db import get_db_url
from sqlalchemy import create_engine, text

eng = create_engine(get_db_url())

def upsert_user(conn, nickname, grade, major, skills, interests, bio):
    row = conn.execute(text("SELECT id FROM fs_users WHERE nickname=:n"), {"n": nickname}).fetchone()
    if row:
        return row[0]
    r = conn.execute(text(
        "INSERT INTO fs_users (nickname, grade, major, skill_tags, interest_tags, bio, created_at, updated_at) "
        "VALUES (:n, :g, :m, :s, :i, :b, now(), now()) RETURNING id"
    ), {"n": nickname, "g": grade, "m": major, "s": skills, "i": interests, "b": bio})
    return r.fetchone()[0]

def upsert_project(conn, title, summary, domains, skills, stage, founder_id, owner_id, hib):
    row = conn.execute(text("SELECT id FROM fs_projects WHERE title=:t"), {"t": title}).fetchone()
    if row:
        return row[0], False
    r = conn.execute(text(
        "INSERT INTO fs_projects (title, summary, domain_tags, required_skills, stage, founder_id, owner_id, "
        "hibernate_reason, hibernate_at, created_at, updated_at) "
        "VALUES (:t, :su, :d, :sk, :st, :f, :o, :h, now(), now(), now()) RETURNING id"
    ), {"t": title, "su": summary, "d": domains, "sk": skills, "st": stage, "f": founder_id, "o": owner_id, "h": hib})
    return r.fetchone()[0], True

def upsert_package(conn, pid, ach, exp, pit, rem, res):
    import json as _json
    ach, exp, pit, rem, res = (
        _json.dumps(x, ensure_ascii=False) if isinstance(x, list) else x
        for x in (ach, exp, pit, rem, res)
    )
    row = conn.execute(text("SELECT id FROM fs_handover_packages WHERE project_id=:p"), {"p": pid}).fetchone()
    if row:
        conn.execute(text(
            "UPDATE fs_handover_packages SET achievements=:a, experience=:e, pitfalls=:pi, "
            "remaining_issues=:r, reusable_resources=:re WHERE id=:id"
        ), {"a": ach, "e": exp, "pi": pit, "r": rem, "re": res, "id": row[0]})
        return row[0]
    r = conn.execute(text(
        "INSERT INTO fs_handover_packages (project_id, achievements, experience, pitfalls, remaining_issues, "
        "reusable_resources, created_at) VALUES (:p, :a, :e, :pi, :r, :re, now()) RETURNING id"
    ), {"p": pid, "a": ach, "e": exp, "pi": pit, "r": rem, "re": res})
    return r.fetchone()[0]

def upsert_case(conn, title, org, summary, domains, ach, award, url):
    import json as _json
    domains = _json.dumps(domains, ensure_ascii=False) if isinstance(domains, list) else domains
    row = conn.execute(text("SELECT id FROM fs_reference_cases WHERE title=:t"), {"t": title}).fetchone()
    if row:
        return row[0]
    r = conn.execute(text(
        "INSERT INTO fs_reference_cases (title, org, summary, domain_tags, achievements, award, url, created_at) "
        "VALUES (:t, :o, :s, :d, :a, :aw, :u, now()) RETURNING id"
    ), {"t": title, "o": org, "s": summary, "d": domains, "a": ach, "aw": award, "u": url})
    return r.fetchone()[0]

def main():
    with eng.begin() as conn:
        # 1. fs_users 增加 contact 列
        conn.execute(text("ALTER TABLE fs_users ADD COLUMN IF NOT EXISTS contact TEXT"))
        print("[1/4] fs_users.contact 列已就绪")

        # 2. 三个组织档案用户（真实组织名，非虚构人物）
        u_yjt = upsert_user(conn, "研支团校友会", "团队", "南京大学研究生支教团（档案·整理自公开报道）",
                            ["教学设计", "活动组织"], ["教育公益", "西部支教"],
                            "档案级账号：南大研究生支教团项目公开资料整理入口，非虚构个人")
        u_byh = upsert_user(conn, "百合站务组", "团队", "小百合BBS站务组（档案·整理自公开报道）",
                            ["社区运营", "站点维护"], ["校园文化", "网络社区"],
                            "档案级账号：小百合BBS公开资料整理入口，非虚构个人")
        u_jzj = upsert_user(conn, "艺术硕士剧团", "团队", "南京大学艺术硕士剧团（档案·整理自公开报道）",
                            ["舞台表演", "剧目运营"], ["校园戏剧", "美育"],
                            "档案级账号：《蒋公的面子》等剧目公开资料整理入口，非虚构个人")
        print("[2/4] 组织档案用户就绪:", u_yjt, u_byh, u_jzj)

        # 3. 三个档案级项目 + 轻量交接包
        p1, n1 = upsert_project(conn, "南京大学研究生支教团", 
            "【档案级·整理自公开报道】1999年组建全国首批研究生支教团，26届青春接力，服务宁夏、甘肃、西藏、云南、贵州、湖北6省10县32所中小学，累计教授学生7万余人、授课30万余课时。这是南大'代代相传'最完整的真实样本。",
            ["教育公益", "志愿服务", "西部支教"], ["教学设计", "活动组织", "沟通协作", "新媒体运营"],
            "fifth", u_yjt, u_yjt, "持续传承中（档案级展示，非休眠）")
        upsert_package(conn, p1,
            ["1999年组建全国首批研究生支教团，连续接力26届", "累计436位研究生志愿者接力（截至2022年）",
             "服务宁夏、甘肃、西藏、云南、贵州、湖北6省10县32所中小学", "累计教授学生7万余人、授课30万余课时"],
            ["以'届'为单位交接：每届离岗前系统整理教学课件、学生档案与当地需求清单",
             "接力式招募：老团员带新团员完成跟岗培养再出征",
             "与当地教育部门建立长期合作，保证服务点位稳定传承"],
            ["初期课程资源分散在各届成员手中，缺乏统一沉淀机制",
             "高原偏远点位轮换时出现过沟通断层"],
            ["支教课程体系的数字化沉淀仍在进行", "受助学生的长期跟踪反馈链条待完善"],
            ["真实报道《26年，接力棒这样传递》（南京大学） https://mp.weixin.qq.com/s/f_bV0pKI5PpIqYg2dX6vLQ",
             "真实报道《南京大学研究生支教团：26年青春接力，向西部而行》（中国青年报） https://zqb.cyol.com/html/2022-08/18/nw.D110000zgqnb_20220818_1-06.htm",
             "服务地清单：6省10县32所中小学（公开报道口径）"])

        p2, n2 = upsert_project(conn, "小百合BBS",
            "【档案级·整理自公开报道】1997年由南大学生自主架设的校园网络社区，累计注册账户38万+，最高同时在线突破1万人，2013年入选'南京大学校园文化十大品牌'。中国高校网络文化的重要样本。",
            ["校园文化", "网络社区", "内容运营"], ["社区运营", "内容运营", "站点维护", "活动策划"],
            "fifth", u_byh, u_byh, "持续运营中（档案级展示，非休眠）")
        upsert_package(conn, p2,
            ["1997年建站，发展为中国高校最有影响力的BBS之一", "累计注册账户38万+，最高同时在线突破1万人",
             "2013年入选'南京大学校园文化十大品牌'"],
            ["站务组代代传承：由在校生志愿者接力运营维护",
             "板块自治文化：版主负责制激发社区自治活力",
             "2005年转型官方实名制后探索高校社区合规运营路径"],
            ["移动互联网冲击导致用户活跃度下滑", "实名制转型期的社区氛围重建成本高"],
            ["移动端体验老化，年轻用户向短视频平台迁移", "27年历史精华帖的档案化整理仍在进行"],
            ["真实报道《一网情深百合开》（南京大学报） https://xiaobao.nju.edu.cn",
             "校史档案：南大校园文化十大品牌名录（2013年评选）"])

        p3, n3 = upsert_project(conn, "话剧《蒋公的面子》",
            "【档案级·整理自公开报道】2011年由文学院本科生温方伊编剧、吕效平执导，为建校110周年创作。从南大礼堂连演三轮一票难求，到全国政协礼堂献演，一届届艺术硕士接力演出至今——校园戏剧'代代相传'的最佳样本。",
            ["校园戏剧", "文学创作", "美育"], ["剧本创作", "舞台表演", "舞美设计", "剧目运营"],
            "fifth", u_jzj, u_jzj, "持续公演中（档案级展示，非休眠）")
        upsert_package(conn, p3,
            ["2012年校庆110周年在南大礼堂连演三轮，场场爆满、一票难求",
             "2013年走出校园在江南剧院开启十年驻场演出，公演62场以上",
             "全国巡演登上北大百年讲堂、全国政协礼堂，从校园话剧成为文化事件",
             "2025年新版舞美升级继续公演，2026年第三期南大戏剧周回归江南剧院"],
            ["以经典剧目为'传帮带'载体：一届届艺术硕士在复排中完成舞台传承",
             "建立'以票房养校内戏剧'的可持续运营模式",
             "保留多版本并行（1.0/2.0/3.0），让每代演员留下自己的诠释"],
            ["校园戏剧经费有限，早期靠师生自筹", "主创毕业后剧目的版权与演出接力需要制度保障"],
            ["新剧本孵化的接力机制仍在探索", "校园演出与商业演出的平衡点待打磨"],
            ["真实报道《校园话剧〈蒋公的面子〉'绝境突围'》（南京大学官网） https://www.nju.edu.cn/info/3321/259861.htm",
             "真实报道《话剧〈蒋公的面子〉：从校园话剧到文化事件》（南京大学官网） https://www.nju.edu.cn/info/3191/160561.htm",
             "江南剧院驻场史：2013-2026南大戏剧周公开报道"])
        print(f"[3/4] 档案级项目入库: 研支团(新{n1}) 小百合(新{n2}) 蒋公的面子(新{n3})")

        # 4. 案例库扩充 7 条南大真实案例
        c1 = upsert_case(conn, "南京大学研究生支教团", "南京大学",
            "1999年组建全国首批研究生支教团，26届接力服务西部6省10县32所中小学，教授学生7万余人。",
            ["教育公益", "志愿服务"],
            "26届接力、436位志愿者、30万余课时", "全国首批研究生支教团组建高校",
            "https://mp.weixin.qq.com/s/f_bV0pKI5PpIqYg2dX6vLQ")
        c2 = upsert_case(conn, "小百合BBS", "南京大学",
            "1997年建站的校园网络社区，38万+注册账户，2013年入选南大校园文化十大品牌。",
            ["校园文化", "网络社区"],
            "38万注册账户、最高同时在线超1万人", "南大校园文化十大品牌（2013）",
            "https://xiaobao.nju.edu.cn")
        c3 = upsert_case(conn, "话剧《蒋公的面子》", "南京大学艺术硕士剧团",
            "2011年学生原创话剧，从南大礼堂演到全国政协礼堂，公演62场以上，一届届接力演出至今。",
            ["校园戏剧", "文学创作"],
            "公演62场+、全国巡演、十年驻场江南剧院", "建校110周年献礼剧目",
            "https://www.nju.edu.cn/info/3321/259861.htm")
        c4 = upsert_case(conn, "南大读书节", "南京大学",
            "南大校园文化十大品牌之一，以阅读推广为核心的校园文化活动，由图书馆与院系接力举办。",
            ["校园文化", "阅读推广"], "入选南大校园文化十大品牌（2013）", "南大校园文化十大品牌",
            "")
        c5 = upsert_case(conn, "拉贝与国际安全区纪念馆志愿讲解", "南京大学",
            "南大校园文化十大品牌之一，师生志愿讲解队接力传播拉贝人道主义精神与国际和平记忆。",
            ["志愿讲解", "和平教育"], "入选南大校园文化十大品牌", "南大校园文化十大品牌",
            "")
        c6 = upsert_case(conn, "南大地学文化节", "南京大学地球科学与工程学院",
            "南大校园文化十大品牌之一，依托百年地学学科底蕴由师生接力举办的地学科普文化品牌。",
            ["学科文化", "科普"], "入选南大校园文化十大品牌", "南大校园文化十大品牌",
            "")
        c7 = upsert_case(conn, "南大校园十大歌星赛", "南京大学",
            "南大历史最悠久的学生文化活动之一，三十余年届次接力，一代代南大人的青春舞台。",
            ["校园文化", "文艺活动"], "三十余年届次接力举办", "南大校园文化十大品牌",
            "")
        print(f"[4/4] 案例库新增: {c1}~{c7}")

        total = conn.execute(text("SELECT COUNT(*) FROM fs_reference_cases")).scalar()
        projs = conn.execute(text("SELECT COUNT(*) FROM fs_projects")).scalar()
        pkgs = conn.execute(text("SELECT COUNT(*) FROM fs_handover_packages")).scalar()
        print(f"\n现状: 案例{total}条 | 项目{projs}个 | 交接包{pkgs}份")

if __name__ == "__main__":
    main()

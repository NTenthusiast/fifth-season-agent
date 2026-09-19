# AGENT.md — 「第五季·续种」校园 AI 传承智能体 · 全局项目档案

> 本文件是项目的**唯一权威档案**：记录项目全貌、技术架构、数据字典、功能清单与每一次变更。
> 每次改动后，Agent 必须在文末「变更日志」追加一条记录（日期 + 版本 + 摘要 + 影响面），保持痕迹可溯。

---

## 一、项目是什么

**「第五季·续种」**——面向高校的校园 AI 传承智能体（南京大学 4 人团队 · 2026 EL 大赛参赛作品）。

核心命题：校园里每年都有大量因**毕业、换届、时间不足**而暂停的好项目（公益服务 / 文化记录 / 工具开发 / 社团活动）。本项目让 AI 智能体「知颜」接管它们的**传承生命周期**：

```
春·萌芽（建档与立项） → 夏·生长（组队与执行） → 秋·沉淀（交接包）
→ 冬·蛰伏（休眠归档） → 第五季·重生（唤醒接棒）
```

- **品牌名**：第五季 / 知颜（释义：知遇每颗种子的心事，为搁置的梦想重新上色）
- **交互形态**：两步式网页——介绍页（档案墙 / 功能全景 / 三大新板块）→ 对话页（与知颜对话完成全部操作）
- **验证口号**：每一场唤醒都有真实数据、真实故事、真实痕迹。

## 二、技术架构

| 层 | 技术 | 说明 |
|---|---|---|
| Agent 框架 | LangChain `create_agent`（v1.0）+ LangGraph | `src/agents/agent.py`，滑动窗口记忆（40 条）+ checkpointer |
| 大模型 | doubao-seed-2-0-**lite**-260215（v6.2 定版：四轮横评 lite/glm-4-7/pro/mini，lite 稳定 4-11s；glm 网关 tool_calls 聚合缺陷、pro 单轮 138s 弃用） | 经平台网关（`COZE_INTEGRATION_MODEL_BASE_URL` + 工作负载身份），SSE 流式；thinking 关闭；sp 6400 字精简版（v6.2 -48%） |
| Web 服务 | FastAPI（5000 端口） | `src/web_server.py`，`/api/chat` SSE + 8 个 REST 端点 |
| 数据库 | 平台 Supabase PostgreSQL | 开发/生产双库隔离；psycopg2 + SQLAlchemy 惰性引擎 + REST 双通道 |
| 对象存储 | S3 兼容（coze_coding_dev_sdk） | 托付书 / 海报 / 截图等产物，24h 预签名 URL |
| 图像生成 | Pillow + 内嵌中文字体 | 托付书 / 种子卡海报纯服务端渲染 |
| 前端 | 原生 HTML/CSS/JS（无框架） | `assets/web/`，花瓣飘落 / 星空 / 四季插图带全 CSS/SVG 实现 |

### 目录速览
```
src/agents/agent.py        # Agent 主逻辑（build_agent）
src/tools/                 # 35 个工具：personal_tools / project_tools / legacy_tools(v3/v4.2) / seed_tools(v8.0)
src/storage/               # memory_saver / database(db, supabase_client) / s3
src/web_server.py          # FastAPI 服务（SSE chat + REST API + 静态挂载）
config/agent_llm_config.json  # 模型配置 + 系统提示词(sp) + 工具清单
assets/web/                # index.html / style.css / app.js / logo.svg
AGENT.md                   # 本档案（变更日志见文末）
```

## 三、数据字典（数据库 13 张业务表）

| 表 | 用途 | 关键字段 |
|---|---|---|
| fs_users | 用户档案 | nickname, grade, major, skill_tags[], interest_tags[], bio |
| fs_projects | 项目种子卡 | title, summary, domain_tags[], required_skills[], stage(spring/summer/autumn/dormant/…), founder_id, owner_id, hibernate_reason |
| fs_project_members | 项目成员（申请-审批制） | project_id, user_id, role |
| fs_project_updates | 项目动态（含申请记录/交接记录） | project_id, user_id, content |
| fs_handover_packages | 交接包 | project_id, achievements, experience, pitfalls, remaining_issues, resources |
| fs_awaken_records | 唤醒接棒记录 | project_id, successor_id, match_reason, awakened_at |
| fs_stories | 传承故事卡（v3） | awaken_record_id, founder/successor_nickname, highlights jsonb, likes |
| fs_awards | 成就定义（v3） | code(unique), name, points, category |
| fs_user_awards | 用户成就（v3） | user_id, award_id（唯一约束） |
| fs_votes | 需求投票（v3） | project_id, voter_nickname（一人一票唯一约束） |
| fs_reference_cases | 真实参考案例库（v4.2） | title, org, summary, domain_tags[], achievements, award, url（14 条全国高校已落地案例，含可跳转官网链接） |
| fs_todos / fs_inspirations | 待办 / 灵感库 | 个人板块 |
| checkpoints* | LangGraph 会话记忆 | — |

### 当前数据规模（开发库）
- 用户 30 / 项目 19（含 6 个外校借鉴案例）/ 故事卡 2 / 唤醒记录 2 / 投票 15+ / 成就定义 7
- 生产库已于 v3.6 全量灌入同一批种子数据（13 张表 163 行，与 dev 库逐表指纹校验一致）

## 四、功能全景（17 项，详细介绍页弹窗同源）

### A. 四季之旅（核心生命周期）
1. **春·萌芽·建档与种子卡**：对话即建档；想法→结构化种子卡
2. **夏·生长·组队与执行**：能力互补匹配、申请-审批制、动态时间线、待办
3. **秋·沉淀·交接包**：AI 提炼五件套（成果/经验/踩坑/遗留/资源）
4. **冬·蛰伏·休眠归档**：连经验一起封存，进入唤醒候选
5. **第五季·重生·唤醒接棒**：三层叙事匹配（种子的故事→为什么是你→第一步），交接后故事自动上墙

### B. 传承宝库（v3 新增）
6. **传承故事墙**：唤醒自动生成故事卡，主页展示+点赞（`/api/stories`）
7. **毕业季托付书**：真实项目数据+寄语 → PNG（Pillow 渲染 → S3 URL）
8. **种子卡分享海报**：领域标签+成果统计 → 分享海报 PNG
9. **项目健康巡检**：休眠超期 / 停滞≥21天 / 待沉淀 三类预警+建议
10. **全校技能图谱**：供需实时聚合，TopN 稀缺/富余（`/api/skills`）
11. **需求投票唤醒**：休眠种子「我也想用」投票，需建档、一人一票（`/api/dormant`+`/api/votes`）
12. **传承者成就**：7 勋章 + 贡献值 + 全校风云榜（`/api/leaderboard`）
13. **跨项目协作发现**：领域相近+能力互补识别牵线

### C. 个人板块
14. **档案画像** 15. **待办管理** 16. **灵感库** 17. **校园议题洞察**（反复被提却无人做的议题聚合）

## 五、Agent 工具清单（35 个）

> ⚠️ 本节此前列的是另一套早已废弃的细分 API（create_user_profile / add_todo / list_todos /
> complete_todo / save_inspiration / create_handover_package / get_handover_package /
> get_recommended_projects / get_collaboration_opportunities 等 12 个工具均**不存在于代码中**），
> 现已按 `src/tools/__init__.py` 的 `ALL_TOOLS` 更正。

- 个人板块（5）：upsert_user_profile, get_user_profile, find_users_by_tags, manage_todo, manage_inspiration
- 校园板块（12）：create_project, search_projects, get_project_detail, update_project, advance_project_stage, add_project_update, add_project_member, save_handover_package, awaken_project, save_match_log, get_reminders, school_issue_insight
- 传承扩展（9）：get_relay_stories, generate_handover_certificate, generate_seed_poster, get_project_health, get_skill_graph, vote_awaken_request, get_my_awards, discover_project_synergy, find_reference_cases（v4.2 新增：检索真实已完成项目参考案例）
- 种子卡生态（5，v8.0）：import_from_github, read_upload, upsert_profile, match_seed_partners, team_overview（seed_tools.py）

注：`get_handover_package` 的功能已并入 `get_project_detail`；`get_collaboration_opportunities`
的实际名称是 `discover_project_synergy`。修改提示词中的工具名时，请以 `ALL_TOOLS` 为准。

## 六、关键 SOP（写入系统提示词，必须遵守）

1. **档案守护边界**：一切档案操作前确认用户已建档；禁止编造用户/项目数据
2. **申请-审批制**：申请入组严禁直接 add_project_member，须以动态记录申请并告知等待发起人审批
3. **权限分级**：托付书/交接包/唤醒等敏感操作仅限发起人或负责人；唤醒需本人确认
4. **响应节奏**：快问快答不绕弯；闲聊不过度调用工具；多需求并行处理；媒体产物用 markdown 图片+媒体卡片呈现
5. **故事/数据转述**：基于真实数字，有温度但不夸张

## 七、运维备忘

- 重启服务：`pkill -f "main[.]py"`（字符类正则防 pkill 自杀）→ `(nohup python3 src/main.py > /tmp/server.log 2>&1 &)`
- FaaS 30 秒启动窗口：DB 连接超时 5s × 3 次重试，checkpointer 失败回退 MemorySaver
- 静态资源已加 `Cache-Control: no-cache`（保 ETag），线上更新后建议用户强刷
- Playwright 验证：executable_path 指定 chromium-1161
- 中文字体：容器内置 Noto Sans CJK；Pillow 渲染用 /usr/share/fonts 下 CJK ttc
- **双库隔离**：dev 与 product 数据库完全隔离；沙箱 PGDATABASE_URL/COZE_SUPABASE_URL 均只指向 dev；product 仅能经 exec_sql(env=product) 中转
- **跨库迁移法**：psycopg2 `cursor.mogrify` 程序化转义导出单条 INSERT（勿手拼 SQL，CSV 展示会把双引号转义成 `""`）；显式保留 ID + `setval` 对齐全部 13 条序列
- **类型陷阱**：fs_stories.highlights 是 jsonb（列表须写 `'["a","b"]'::jsonb`，空值是 `[]` 非 `{}`）；fs_project_updates 外键列名是 author_id（非 user_id）；fs_projects.stage 值域是季节名（winter/spring/summer/autumn/fifth）

## 八、变更日志（每次改动在此追加）

| 日期 | 版本 | 摘要 | 影响面 |
|---|---|---|---|
| 2026-09 初 | v1 | 项目立项：五季生命周期 MVP、双页结构、核心工具链 | 全量 |
| 2026-09-10 | v1.1 | 部署启动超时修复（DB 5s×3 重试）；统计真实化（删心跳假增长，API 直连）；Supabase 503 四层容错 | memory_saver / db / web_server / app.js |
| 2026-09-11 | v1.2 | 五项 UI 优化（艺术字光晕/边框特效/星空背景/四季过渡带/季节×功能融合按钮）；花瓣卡顿+抖动修复（60FPS） | index.html / style.css |
| 2026-09-12 | v1.3 | 项目库扩充 2→12（10 发起人+10 项目+成员/动态/交接包）；成员申请-审批 SOP 上线 | 数据库 / sp |
| 2026-09-13 | v2 | 采纳用户包同步：sp 守护边界+冲突防护+结构化输出、名字释义「知遇+颜色」、文案润色 | config / index.html |
| 2026-09-14 | v3 | **八大新功能**：故事墙/托付书/海报/健康巡检/技能图谱/投票/成就/协作发现；4 新表+5 新 API；Agent 提速（thinking off+节奏守则）；功能全景弹窗；富媒体气泡卡片 | legacy_tools.py(新增) / web_server / agent.py / 三大前端板块 |
| 2026-09-14 | v3.5 | ①专属 SVG Logo（五瓣续种花环：四季节+第五季紫芯新芽）+导航/英雄区/favicon 三处集成 ②季节 chips 单行不换行修复 ③项目库 12→19（借鉴沈阳城市学院绿岛智循/广东女院蓝信封/西北农林衣旧情深/塔里木大学春日打卡等外校真实案例，含 8 新用户+18 条动态+13 成员+投票）④功能介绍弹窗全面加深（每项功能详述+对知颜说什么示例）⑤高级感升级：四季笺插图带/金线内衬+角部雕花/标题边饰/渐变字/页脚四季彩带 ⑥创建本 AGENT.md | index.html / style.css / 数据库 / AGENT.md(新建) |
| 2026-09-14 | v3.6 | **生产库（product）种子数据全量灌入**：13 张表 163 行与 dev 库逐表 md5 指纹校验完全一致；显式保留源库 ID（含历史缺口 21/23/25），13 条 ID 序列 setval 对齐防后续插入撞号；修复 v3 遗留的 18 条动态+13 条成员关系静默缺失（列名 user_id→author_id）；迁移方式：psycopg2 程序化转义导出单条 INSERT（沙箱无法直连 product 库，经 exec_sql 中转） | product 数据库 |
| 2026-09-14 | v4.0 |**智能体根因修复 + 全站语域治理 + 参赛交付物补齐**：①模型由误配的 `glm-4-7-251222` 改回 `doubao-seed-2-0-pro-260215`（头号"变蠢"原因）；②修复 `agent.py` 读错配置键（`thinking` vs `thinking_type`）导致 thinking/max_tokens/frequency_penalty 长期失效；③修复滑动窗口 `[-40:]` 切断 tool_call/ToolMessage 配对引发网关 400 的隐患；④收窄 `_DB_FAULT_KEYWORDS` 过宽判据（原含 "connection"/"timeout"，使普通工具报错被误判为记忆库故障）；⑤Supabase 客户端改为全局复用（原每次调用新建 httpx 客户端，单次 `get_project_detail` 建 4 个）；⑥sp 新增高权重「表达规范」（克制语域 + 禁用清单 + 正反示例 + 借鉴咨询师工作方式而非身份）与「工具路由表」；⑦`model.py` 补齐 4 张缺失表（9→13，与代码查询完全对齐）；⑧前端修复移动端无导航、hero 标题被裁切、`--ink-faint` 未定义、对比度 2.63:1、grid 固定下限溢出等；⑨删除 6 处不可核验外链与页脚错误年份 2025；⑩新增 SSE 工具进度事件；⑪新建 `docs/项目文档.pdf`（13 页）、重写 README、`.gitignore` 放行 `docs/`；⑫修正本档案工具清单（12 个幽灵工具）与表数量矛盾 | config / agent.py / web_server.py / tools / supabase_client.py / model.py / index.html / style.css / app.js / README / .gitignore / docs / AGENT.md |
| 2026-09-15 | v4.1 | **上传版全量同步至工作区并完成沙箱运行时验证**（改动报告全部事项落地）：覆盖 12 个修改文件 + 新增 `docs/项目文档.pdf`/`项目文档.html`/`scripts/preview_mock.py`/`改动报告.md` + 删除 test1.png×2 + 同步 `.gitignore`；运行时验证（改动报告第七节必查项）：①文泉驿中文字体存在（托付书/海报不会豆腐块）②启动日志确认 model=doubao-seed-2-0-pro-260215/temp=0.4/thinking=disabled/tools=25 实际生效 ③Playwright 移动端 320/375/768px 无横向溢出、hero 标题不出界、汉堡菜单展开 7 锚点/外部点击/Esc 三路收起、全站无 JS 报错 ④test_run 工具路由准确（建档→检索→详情三步链）、语域收敛 ⑤SSE tool 事件帧前后端契约对齐 | 全量（12 覆盖 + 6 新增 + 2 删除） |
| 2026-09-15 | v4.2 | **八项需求迭代（参考案例库 + 推理规划人格 + 首屏视觉重塑）**：①新表 `fs_reference_cases`（14 条全国高校真实已完成案例：蓝信封 210 万封信/南大雪域寻音挑战杯特等奖/川农旧衣递温情/成都大学衣旧情深 2000 件/兰州理工绿色捐衣等，全部带可跳转官网链接，dev+product 双库同构同数据）②新工具 `find_reference_cases`（25→26 个，打分排序：标签命中 8 分/关键词 3 分/字符兜底）③sp 重写（9119→11288 字）：人格由克制学长转为温柔学姐（记得住/想在前/说得软做得实），新增「需求推理」三段式（能力盘点→需求映射→匹配推荐，显式呈现推理链）与「成长规划」（阶段拆解+本周第一步+风险提醒）两大核心能力，「建卡即送参考」SOP（想法落定即检索 1~3 个同类真实案例以 Markdown 链接呈现），语气词定量放宽（≤2 个/回复）+ 句末 emoji 严格禁止（两轮强化后收敛）；④首屏「第五季·续种」大字：去 drop-shadow 阴影、去 charFloat/gradFlow/dotBlink 持续动画（仅留 charRise 一次性入场，字体落定后完全静态），新增 art-halo 紫金双色静态光环，粒子 8→12（新增金/粉两色系），artSweep 扫光改 transform 实现防重排；⑤排版与字体分层：6 区块标题专属渐变分色（规则紫/四季四色/唤醒暖橙/双板块靛蓝/技能青绿/投票紫金）、副题统一楷体、hero 区手写 STKaiti 栈统一为 var(--font-kai)、hero-badge/chips-label 启用幼圆（--font-round 首次上岗）、知/颜二字紫金分色；⑥艺术感：AI 气泡暖白纸感渐变+紫粉微光斑+楷体小标题、hero 底缘四季色光带；⑦`model.py` 补 FsReferenceCase ORM（13→14 类）⑧验证：Playwright 计算样式断言（charAnim=charRise/filter=none/粒子 12/标题渐变生效）+ curl SSE 全文验证案例链接 + test_run 三轮（推理链 95/90/85 匹配度+真实案例+温柔语气+emoji 收敛） | config / legacy_tools.py / __init__.py / model.py / index.html / style.css / 双库 fs_reference_cases / AGENT.md |

> **下次改动请从这里继续追加** —— 一行日志，让每一次进化都有迹可循。

## 变更日志

### v10.0 · 十项新需求：个人项目库/团队空间完善/交接包授权/招募详情/海报灯箱/手册教程重写（2026-09-19）
- **个人项目库（需求⑦⑨）**：新表 `fs_personal_projects`（title/summary/description/status/tags/handover_package JSONB/handover_public，编号 PJ-#N，仅本人可见）；`/api/my-projects` GET/POST/PATCH/DELETE；Agent 新工具 `manage_personal_project`（create/list/detail/update/delete/generate_handover/set_public——知颜基于项目档案提炼五段式交接包+治理声明落 JSONB）与 `get_public_handover`（FS-#N/PJ-#N 凭编号获取，未公开如实提示需主人授权）；种子库第三 tab「📁 我的项目库」：新建表单/状态标签/生成交接包引导（跳对话预填）/公开开关/删除；交接包与项目信息由项目库统一管理
- **公开交接包授权（需求⑧）**：`fs_projects` 加 `handover_public` 列，43 个存量项目全部置 TRUE（scripts/seed_v100_handovers.py 为 31 个无包项目补五段式交接包，packages=44）；新项目默认不公开，需主人授权；公开种子卡角标区分「交接包可获取/需授权」；`/api/projects/{id}` 未授权时 handover 置空并返回 handover_locked（发起人/负责人不受限）；公开库合并展示已公开 PJ 卡 + `/api/handover/personal/{pid}` 他人获取端点
- **团队空间补完（需求③）**：新表 `fs_team_chat_messages` 持久化团队共享对话（/api/chat 团队分支把每期用户+知颜消息落库）；`GET /api/teams/{tid}/chat` 打开团队空间加载全队历史互相可见（气泡区分 我/他人/知颜）；成员列表每项加「✉ 留言」→ `/api/messages/send`（复用 fs_messages 信箱）；共享记忆线程 team-{id}-chat 原有
- **招募详情（需求①）**：团队详情新增「🌱 项目现状」区块（关联项目 stage/简介/领域/所需能力+查看完整种子卡）；海报自适应（≤300px）+ 点击放大灯箱（#poster-lightbox，修复 display:flex 覆盖 hidden 的真 bug：补 `[hidden]{display:none}`）
- **引入卡管理（需求④）**：公开卡详情加「🌱 引入我的种子库」；引入卡加「移除」按钮 → `DELETE /api/projects/{pid}/unimport`；修复 v9 真 bug：引入卡按钮用 `s.id`（undefined）应为 `s.project_id`；fs_project_members 加唯一索引 (project_id,user_id) 并清重复行
- **种子卡详情（需求⑤）**：个人种子卡点开弹窗（灵感原文/标签/状态/关联项目 + 一键「和知颜聊聊这个灵感」）
- **UI 微调（需求②⑥）**：候选池「展开 +N」缩为标题行内 26px 小胶囊（不再独占网格一整格）；nav-cta 补 border:none 修复浏览器默认灰黑边框 + 全站按钮 focus-visible 软高亮
- **手册与教程重写（需求⑩）**：功能手册扩至十节（新增「个人项目库」「知颜对话模拟」——7 组照着说就能用的对话示例）；新手教程扩至 10 步（含项目库/交接包获取步骤与知颜能力示例）
- **自部署加固**：agent.py 凭据优先级改为自有 Key 优先（FS_LLM_API_KEY/OPENAI_API_KEY 一旦配置即覆盖平台网关，base_url 与所选 key 配对）——平台积分耗尽时配 .env 即恢复
- **测试**：后端 API 回归 15 项全过（项目库 CRUD/工具生成交接包/公开授权开关/PJ 卡入公开库/他人获取/取消公开 403/工具层授权锁/FS-017 存量可读/引入移除/团队详情项目现状/聊天历史/成员留言）；Playwright 31/31 全过（十项需求逐一断言）；测试数据已全部清理（临时团队/项目/留言/引入行）
- **已知环境限制**：平台 LLM 积分余额耗尽（错误码 301001），/api/chat 与 test_run 的 LLM 路径暂不可用（非代码缺陷；配置自有 FS_LLM_API_KEY 即恢复），全部非 LLM 功能经 API/工具直调/Playwright 充分验证

### v9.0 · 十项体验与功能升级：顶栏排版/用户隔离/候选池折叠/公开库折叠/档案故事/组队招募/风云榜积分/功能手册/引入卡（2026-09-18）
面向用户十项需求的整版迭代（顶栏排版、本地用户隔离、候选池每类型 1+展开、公开库折叠、故事墙扩容点开全文、档案墙按钮移位、组队招募海报、风云榜积分规则、完整功能手册、个人库引入区）：
- **①顶栏排版**：logo「第五季·续种」改行楷字体栈（STXingkai/华文行楷/楷体）；nav-links 全部功能入口统一胶囊边框 + white-space:nowrap（单模块文字同一行）+ flex-wrap:wrap（一行放不下自动列成两行）；≤1020px 时 nav-inner 换行让导航独占一行
- **②本地用户隔离**：saveAuth 检测昵称变化（含登出）即 resetSession()+清空对话气泡+重现引导语；logout 关闭全部身份相关弹窗（team/profile/story/group/leaderboard/handbook/recruit 7 个，修正 v8 遗留的 type-modal/lb-modal/manual-modal 旧 ID 错配）；Playwright 双断言（登出后我的团队/引入区不残留）
- **③候选池折叠**：loadDormant 重写——dormantGroups 按 domain_tags[0] 分 12 类，每类型仅渲染票数榜首 1 张卡 + 「📁 展开其余 N 个」虚线卡；点开 group-modal 弹窗展示该类型全部休眠项目（votes-grid group-modal-grid）；休眠项目库 31→43（新增 12 个：南雍拾光失物招领/深夜自习室空位地图/飞花令诗词/铁翼机器人训练营/瞰南雍无人机航拍/仙林跑团/中文角/先生的书桌/雨洪花园/指间书页盲文图书角/鼓楼层音乐节/南雍食验室，经 scripts/seed_v90_data.py 灌入，覆盖公益/科技/文化/体育/生态/无障碍等 10+ 新类型）+ 29 张示范投票；/api/dormant limit 12→60
- **④公开种子库折叠**：FOLD_N=6 默认只显 6 张，seeds-public-toggle 按钮切换全部 43 张（window.__FS_PUB_SEEDS 缓存 + dataset.folded 状态）
- **⑤档案故事墙**：新表 fs_curated_stories（7 篇跨校真实传承故事：一场跨越二十六年的接力/研支团/蓝信封书信陪伴/旧衣回收/口述史等，含 era/school/tags/story_full/source_url，文本在事实基础上文学润色）；_stories_query 双流合并（kind=archive 档案故事 id=100000+real_id 供点赞键区分 + kind=awaken 唤醒实录）；新端点 GET /api/stories/{story_id} 详情；前端 story-archive-card 点开 story-modal 弹全文（分节渲染 + 来源标注 + 精选星标）
- **⑥档案墙按钮移位**：archive-toggle-wrap（展开传承故事）移至「南大传承实录」nju-strip 上方
- **⑦组队招募完善**：fs_teams + poster_url TEXT（base64 dataURL ≤2.5MB 直存，FileReader 前端生成）；POST /api/teams 支持 poster 字段；新端点 PUT /api/teams/{tid}/poster（仅队长可换）；/api/teams 匿名可访问（招募区所有用户可见，未登录 my_teams 空）——修正 v8 登录门槛违背需求的问题；recruit-modal 发布弹窗（队名/说明/海报上传预览/删除）；招募卡与我的团队卡展示海报；团队详情 team-poster-box（海报大图 + 队长「更换/上传海报」入口）；index.html 补 v8 遗漏的 team-poster-box 容器
- **⑧风云榜积分体系**：compute_all_user_points 重写为 **13 条严格积分规则**（档案建立+5/唤醒接棒+30/双料传承人+50/发起项目+10/多产发起人+30/沉淀交接包+15/项目完成传承+40/为种子投票+5/投票召集人+20/存个人种子卡+5/引入公开种子卡+15/团队组建成功+20/留言牵线+2 封顶20），POINT_RULES 常量与 docstring 同源；每用户输出 breakdown 积分构成标签（如「多产发起人 · 发起×6 · 完成传承×3」）；/api/leaderboard?full=1 返回 top50+rules；前端 lb-card 完整榜单弹窗（前三名奖牌+行内构成+「看画像」只读查看公开画像用户/「画像未公开」占位）；规则区由后端动态渲染（删前端硬编码旧 6 条文案，杜绝前后端不一致）
- **⑨完整功能手册**：HANDBOOK_HTML 常量（8 大板块详细分点：身份与档案/与知颜对话/种子库体系/项目传承链路/组队空间/传承故事与档案/风云榜/新手引导，覆盖注册登录/传承码/画像公开/上传/搜索引入/双种子卡/导入代码/投票/接棒/交接包/留言/招募/申请/团队对话全部能力 + 建议路线）；导航栏「功能手册」按钮 → handbook-modal 惰性渲染
- **⑩个人库引入区**：_my_seed_cards 扩展 introduced 查询（fs_project_members join fs_projects，带 FS 编码/票数/发起人/交接包标记）；/api/seeds/mine 返回 imported 数组；前端 seeds-intro-grid「🤝 我引入的公开种子卡」子区（绿边卡 + 空态引导）
- **v9.0 CSS 全量**（style.css +223 行）：顶栏行楷/胶囊边框、votes-group-more 虚线展开卡、story-archive-card/story-detail-card 详情、seeds-fold-toggle、seeds-intro-card、recruit-card/recruit-poster-*、team-poster(-big)、lb-open-btn/lb-card/lb-row/lb-rules、handbook-card/hb-hero/hb-sec、小屏适配
- **验证**：API 链路（stories 合并 12 张=7 档案+5 唤醒/详情全文 322 字/leaderboard full 45 人 13 规则+breakdown/import 项目/seeds mine imported/建队带海报/换海报 PUT）+ Playwright **50/50**（十项需求全覆盖）+ 最终回归 9/9（匿名招募区/匿名风云榜/注册→发布招募→登出→匿名仍可见队与海报）+ test_run（新用户建档发码 471985 + 新休眠项目检索呈现）；测试用户（测试玖/测试拾/匿名验收官/匿名验收员乙/验收员9621/回归验收官）、测试团队（6-12 号）、测试线程、/tmp 上传全部清理

### v8.0 · 种子卡生态 + 组队空间 + 个人画像 + 文件建档 + 新手教程（2026-09-18）
面向"温柔首话/双种子卡/导入上传建档/组队协作/候选池分类/跨项目牵线/画像公开/新手教程"八项需求：
- **温柔首话（需1）**：fs_users 新增 intro_done 标记；/api/chat 检测首次对话注入 `[这是与该用户的第一次对话]` 提示——知颜自我介绍名字由来（知遇+颜色）与功能全景，再温柔询问年级/专业/擅长/兴趣，收集后建档（upsert_user_profile）并生成画像（upsert_profile）；SSE done 后置 intro_done=True（引导仅一次，此后延续旧记忆）；实测首话 4.8-5.9s 含名字由来+功能+问询
- **双种子卡体系（需2）**：①个人种子卡——复用 fs_inspirations（+title/tags 列），编号 **seed_code={传承码}-{id:03d}**，仅本人可见（/api/seeds/mine 校验归属，他人查空）；manage_inspiration 升级 title/tags 参数②公开种子卡——项目档案即种子卡，编号 **FS-{project_id:03d}**（/api/seeds/public 返回 29 张，带 has_handover/votes/owner 画像公开标记）；前端 seeds-section 双 Tab（我的种子卡/公开种子库），我的卡带"🔒 仅你可见"徽标
- **导入代码+上传文件建档（需3）**：新工具 **import_from_github**（GitHub API 抓仓库元数据+README 3000 字，404/私有如实报错，透传网关 Authorization）；`POST /api/upload`（multipart，≤15MB，解析 txt/md/csv/json/代码/pdf(pypdf)/docx(docx2python) → /tmp/fs_uploads/{file_id}.json 登记）+ 新工具 **read_upload** 读全文；前端 chat 上传按钮 → 自动发送含 file_id 的建档指令（知颜通读→整理→不明晰处温柔追问）；**关键坑：fastapi.UploadFile 是 starlette 子类，form 解析返回 starlette 实例，isinstance 反查 False → 必须对 starlette.datastructures.UploadFile 判断**
- **组队空间（需4）**：新表 fs_teams(id/name/description/leader_id/project_id/status) + fs_team_members(UNIQUE(team_id,user_id))；建队（队长自动 approved）→ 申请（dup 处理+队长信箱自动收到含申请人画像摘要-if公开的申请留言）→ 队长审批（通过/婉拒均自动留言通知；≥2 approved 团队转 active）；**协作空间**=/api/chat 传 team_id → 校验成员资格 → 切换共享线程 **team-{id}-chat**（知颜保留全队共同记忆）+ 团队身份注入 `[团队协作空间「队名」｜成员：...｜本期发言者：...]`；前端 teams-section（我的团队/招募中两区）+ team-modal（成员列表/待审批含画像与申请说明/协作空间 SSE 对话区）
- **候选池分类排序（需5）**：loadDormant 重写——按 domain_tags[0] 分组、组内 votes 降序、组间按组内最高票排序；每卡新增"种子卡"按钮（data-view-seed→详情弹窗）+ 投票信息保留；详情弹窗升级：标题带"公开种子卡 FS-#N"编号 + pd-actions-row 两按钮（✉给发起人留言=跳对话预填留言指令 / 🤝发起组队=prompt 队名→建队）
- **跨项目牵线（需6）**：新工具 **match_seed_partners**——技能缺口计算（我的项目所需技能-我已掌握）→ 评分（fill×3+interests×2+shared）→ 返回 partner_candidates 与 project_pairs；sp 规定知颜**先征得双方同意**再 send_message 牵线留言
- **个人画像（需7）**：fs_users 新增 persona(jsonb)/profile_public；新工具 **upsert_profile**（traits/strengths/story/goals 四维，第二人称描述）；`GET/PUT /api/profile`（本人编辑+公开开关）、`GET /api/profile/{nickname}`（**仅对方公开时返回**，否则 403）；画像公开后在项目发起人处（详情/公开种子卡 owner_profile_public）、组队申请时（队长信箱申请留言自动附画像摘要）可见；前端 profile-modal 四 textarea+公开开关+保存回填；导航栏画像按钮（人形铃铛）
- **新手教程（需8）**：nav-tour 按钮 + TOUR_STEPS 8 步（登录/对话/候选池/种子库/组队/引入/图谱/信箱画像）+ 聚光灯引导（getBoundingClientRect 定位、box-shadow 4000px 遮罩、上一步/下一步/跳过/Esc/→键）
- **修复三连**：①supabase-py 新版 `.order(col, asc=True)` 不兼容 → `desc=False`（建队接口曾 500）②上传 isinstance 判型（见上）③**登录/注册/退出后认证相关区块不刷新**——saveAuth 不触发重载，新增 refreshAuthSections()（loadDormant+loadSeeds+loadTeams）挂到 doLogin/finishRegistration/logout 三处；另修教程第 2 步选择器 #chat-panel 不存在（实际 view-chat）→ .nav-cta、末步 #nav-auth .nav-bell 登出态隐藏 → #nav-auth
- **agent 侧建档补传承码（test_run 发现）**：upsert_user_profile 原先建的用户无 legacy_code（种子卡编号回退 000000-xxx 且无法登录）→ 新增 _gen_legacy_code（与 web 端同规则 50 次重试查重），建卡返回 legacy_code_note 提醒转告用户
- **工具与 sp**：新文件 src/tools/seed_tools.py（import_from_github/read_upload/upsert_profile/match_seed_partners/team_overview 五工具，全站 35 个）；sp 7924 字/33 工具行——SOP0 首话+团队空间段、SOP10 种子卡生态（导入建档温柔追问/文件建档/种子对牵线征同意/团队答疑）、路由表+7 行
- **验证**：API 27 项（注册/首话自我介绍+intro_done 一次性/二话建档+画像四维/种子卡编号=传承码-序号+仅本人可见/上传 file_id/建队-申请-信箱通知-审批-active-团队线程对话/画像公开与 403/公开种子卡 FS 编号）+ Playwright **38/38**（教程 8 步含跳过/候选池分组降序/注册传承码/空态引导/详情 FS-#N+双按钮/留言预填/prompt 建队/团队空间弹窗/画像编辑公开保存回填）+ test_run 两轮（新同学→建档自动传承码 441843→画像→种子卡 441843-008→自我介绍名字由来）；测试用户 11/团队 5/消息/灵感/投票/checkpointer 线程（45+75+63 行）/上传文件全部清理
- **运维注记**：平台托管服务与手动实例并存时，**pkill 正则会匹配到同一命令串里 nohup 后半段的字面 "python3 src/main.py" 导致 shell 自杀**——pkill 与启动必须分两次 exec 执行；平台网关 9000 直连 curl 返回 401 invalid token（需网关 token），沙箱内验证一律走 5000 直连

### v7.0 · 传承码账户体系 + 留言信箱 + 持久记忆 + 真实项目库（2026-09-18）
面向"注册登录/记忆持久/留言连接/登录门槛/项目扩充/报道溯源"六项需求：
- **注册登录（需1）**：fs_users 新增 legacy_code（六位数字传承码，全库唯一）与 school 列；`POST /api/auth/register`（昵称+年级+专业，年级格式 ^20\d{2}级$）→ 传承码**仅注册时一次性完整展示**（前端 acr-code 大字号 + 强抄写提示）；`POST /api/auth/login`（昵称+传承码，返回用户档案与未读数）；存量 42 用户已回填随机传承码
- **认证传输（关键坑）**：浏览器 fetch **禁止 header 值含非 ASCII 字符**（中文昵称直接 throw，loadDormant 曾静默失败）→ 认证改走 **fs_auth cookie**（`encodeURIComponent(JSON{n,c})`，SameSite=Strict，7 天）；服务端 _auth_user 优先读 X-FS-Nickname/X-FS-Code 头（ASCII 昵称/curl 测试用），缺失时解析 cookie；header 中文的 latin-1→utf-8 修复用 _hdr_utf8
- **记忆持久化（需2）**：checkpointer 早已是 PG PostgresSaver 优先（storage/memory），v7.0 将对话线程从随机 session 改为 **user-{id}-{nickname} 绑定**——换设备/重启服务/隔周回来记忆不清零；/api/chat 每条消息自动注入 `[当前登录用户：昵称（年级 专业）]` 前缀，知颜开箱即知用户身份（SOP0 已改写，不再问"你是谁"）；验证：cookie 重连后知颜记得上轮留言内容
- **留言信箱（需3）**：新表 fs_messages(id/sender_id/receiver_id/content/is_read/created_at)；新工具 **send_message**（from_nickname 用当前登录用户，严禁冒充；内容润色至 100 字内）/ **check_my_inbox**（查询后自动置已读）；`GET /api/messages/inbox` + `GET /api/auth/me`（未读数）；导航栏铃铛徽标 + 信箱弹窗（inbox-item/inbox-empty）；sp 新增 SOP9 留言信箱与工具路由表两行
- **登录门槛（需4）**：对话/投票/引入接棒全部 requireAuth——未登录点击弹认证层（登录成功自动续行原操作，对话自动重发）；投票身份取自登录态（不再信任 body 昵称）；dormant 按登录用户返回 voted 已投态（登录后"✓ 已投" disabled，刷新从服务端恢复）；退出登录清 cookie+localStorage+气泡历史
- **真实项目库扩充（需5/6/7）**：fs_projects 新增 school/source_url/source_name 列；入库 6 个**有公开报道的南大真实项目**（#24 大山里的孩子在编程·科技星火计划-互联网+金奖 / #25 雪域寻音·援藏口述史-挑战杯特等奖 / #26 青年讲中国·国际学者访谈-挑战杯特等奖 / #27 和园银龄数字课堂 / #28 小小银行家·少儿财商课堂 / #29 南商筑梦团·基层支教实践），founder 为档案级账号"校史档案室"（id=48）；#24/25/26 补档案级交接包五件套+治理三声明（achievements 含真实数据：672节教案/146位受访者/101位学者）
- **搜索优先级（需5）**：/api/projects/search 排序规则 = 本校项目优先 → 有交接包（建档过）优先 → 原顺序（搜索"支教"验证：#20 研支团(本校+包) → #24 星火计划(本校+包) → #29 筑梦团(本校)）；import-card 显示"本校/有交接包"徽标（ic-school 绿/ic-handover 棕）；详情弹窗新增 pd-source 报道区块（source_name 可点击跳 source_url，注明"版权与事实以原发布方为准"）
- **前端认证体系**：Auth 模块（loadAuth/saveAuth/authHeaders/requireAuth Promise 弹层）；auth-modal（登录/注册 Tab + 年级▲▼滚动选择 2015-2035 + 传承码一次性展示页）；nav-auth（登录按钮 ↔ 昵称+铃铛+退出）；对话 401 自动弹认证层并重发；欢迎语改为"我已经认出你了"（登录用户版）+ 新增 04·我的信箱 starter
- **验证**：API 链路 12 项（注册/重复拦截/错误码/正确登录/未登录401/身份注入/留言投递/信箱查询自动已读/未读数归零/投票登录态/搜索优先级/详情source）+ Playwright **20/20**（含投票已投态刷新恢复）+ test_run（并行查信箱+真实留言投递）；测试用户/留言/投票已清理

### v6.2 · 性能根治 + 技能图谱标签墙 + 项目引入与权益治理（2026-09-18）
面向"响应速度 / 模型选型 / 图谱可读性 / 投票公平 / 权益保护 / 项目引入"六项需求的系统性升级：
- **性能根治（需1）**：根因是 **PID 278 僵尸进程**（08:33 以绝对路径 `python /workspace/projects/src/main.py` 启动的旧实例，uvicorn reload watcher 常驻 57.8% CPU 饿死 worker 事件循环）——报昵称 116s/建档 138s 的真凶；`pkill -f "python3 src/main.py"` 因 python≠python3、路径形式不同从未匹配到它。kill 后：报昵称 4.8s→**2.9-6.3s**、建档全链路 **11.3s**（含真实 web_search）。经验沉淀：服务必须 `COZE_PROJECT_ENV=PROD` 直启（禁用 reload），杀进程用 `pkill -9 -f "python3 src/main[.]py"`（方括号防 shell 自匹配）
- **模型评测定版（需2）**：doubao-seed-2-0-**lite**-260215（历经 glm-4-7 → pro → mini → lite 四轮横评）。GLM-4-7 弃用原因：网关非流式返回 str 非对象 / thinking 输出进 reasoning_content / create_agent 层 tool_calls 流式聚合失败（最小场景 6/6 但完整 agent 28 工具 4/4 失败）/ 多轮工具对话第三轮在网关 hang 死；pro 弃用原因：单轮 LLM 调用实测 138s（日志时间戳证实）；lite 稳定且 4-11s 达标。**sp 精简 12391→6400 字（-48%）**，保留全部路由/分流/治理/六维/三步确认规则；SOP0 改写为"昵称+get_user_profile 与其余所需工具**同一轮并行调用**；get_reminders 仅冷启动破冰时才调用"；agent.py 修复 thinking_type 键名不匹配（此前从未生效）
- **技能图谱标签墙（需3）**：移除条形图，改为 skill-chips 标签墙（24 技能，chip-scarce 红边框稀缺/chip-rich 绿边框富余/chip-even 均衡）；技能弹窗项目行（sp-proj）带 data-proj-id 可点击 → openProjectDetail 种子记忆卡详情弹窗（STAGE_LABELS 五季中文名）
- **投票公平性（需4）**：初始一律"我也想用"未投态（移除 localStorage fs_voted 锁定）；投票时 askNickname 输入昵称 → 服务端 (project_id, voter_nickname) 唯一约束去重计票，一人一票防刷
- **权益治理三声明（需5）**：save_handover_package 拒绝缺项（sp 强制校验）；详情 API 从 reusable_resources 的【授权范围】/【资源有效期】/【原团队权益】前缀解析三声明；DB 已为南大档案包 20/21/22 补录（档案级整理授权/长期有效/原团队保留署名归属）；详情页 pd-gov 绿色权益区块展示
- **项目引入模块（需6）**：主页新增 import-section——`GET /api/projects/search?q=`（title/summary ilike + domain_tags/required_skills 内存兜底，关键词出相关项目、项目名精确命中）、`GET /api/projects/{id}`（种子记忆卡详情：发起人/五件套/治理三声明/成员记录）、`POST /api/projects/import`（校验昵称已建档/非本人项目/唯一约束去重，fs_project_members role=接棒人）；前端 import-card 网格 + 查看种子卡 + 引入接棒（昵称确认→成功弹窗说明三步确认与原团队信息保留）；路由顺序 search/import 先于 {project_id} 注册
- **修复 maybe_single 406 击穿（关键）**：该网关 PostgREST 对 0 行 maybe_single 返回 406 PGRST116 而非 200+null，`find_user_by_nickname`/`find_project`/`require_project_membership`/web_server 8 处全部被 APIError 击穿——新用户查档报"查询用户失败: JSON object requested..."导致 LLM 不走建档路径。db_helpers.py 新增 `safe_maybe_single()`（PGRST116/"multiple (or no) rows" 规整为 None），全部调用点替换；详情查询的 handover 改 order+limit 1 防多份档案包 406。修复后：苏念安不存在 → `exists:false` 引导 → LLM 正常建档（id=47 标签正确）
- 验证：Playwright 前端 18/18（标签墙 24 技能/条形图移除/技能弹窗 5 项目/项目详情种子卡/投票初始全未投/昵称确认/引入搜索"科普"2 结果/"蒋公的面子"精确命中/权益三声明可见/接棒昵称弹窗）；test_run 全链路（并行查档+六维解释 45 分+三步确认+真实 GitHub 三项目）；/api/projects/20-22 治理三声明非空；import 拦截未建档昵称

### v6.1 · 数据真实性扩充 + 意图分流 + 前端交互升级（2026-09-18）
面向"数据规模与真实性"的十项需求系统性响应（南大档案入库 / 轻量交接包 / 意图分流 / 昵称前置）：
- **数据分级与南大档案入库**（scripts/seed_nju_archive.py）：fs_users 新增 contact 列；3 个**组织档案账号**（研支团校友会 38 / 百合站务组 39 / 艺术硕士剧团 40，bio 注明"档案级账号·整理自公开报道·非虚构个人"）；3 个**档案级项目**（20 研支团 / 21 小百合 BBS / 22 蒋公的面子，summary 带【档案级·整理自公开报道】前缀）各配轻量交接包（五件套含真实报道 URL）；7 条南大案例（15-21，读书节 / 拉贝纪念馆 / 地学文化节 / 十大歌星赛等）→ 全库计案例 21 条 / 项目 22 个 / 交接包 9 份
- **修复 PG 数组字面量缺陷**：psycopg2 直传 list 会被写成 PG 数组 `{a,b,c}` 而非 JSON 数组，导致 /api/handover 五件套解析全 0——seed 脚本 upsert_package/upsert_case 内部改 json.dumps，已入库数据已修复
- **轻量交接包范式**（需1）：五件套承载"方向 / 已解决的核心问题 / 可复用资源"三段式轻量记录，目的在匹配同方向的人而非交接完整代码——sp 已写入该定位
- **对话空响应兜底**（需2，web_server.py）：日志证实模型偶发 200 但零文本 chunk（reply_chars=0，多发于工具调用后一轮）——collected 为空时追加 HumanMessage 提示重试一次流式；_stream 增加 payload_override 参数
- **search_github_projects 工具**（需2，legacy_tools.py）：真实 GitHub Search API（api.github.com/search/repositories，超时 15s，无 token 可用），返回 name/url/direction/language/stars/topics/solved_hint——实测检索正常；**find_mentors 工具**（需5，personal_tools.py）：按标签重合度排序推荐前辈，contact 仅在用户自愿公开时展示，过滤档案级组织账号
- **contact 自愿公开字段**（需5）：upsert_user_profile 新增可选 contact 参数（docstring 注明绝不主动索要）；已建档人可被 find_mentors 推荐给后来人
- **sp 意图分流 5.6 节**（11427→12419 字）：五种新人意图分路——接手项目（建档+search_projects）/ 有项目托付（create_project+save_handover_package）/ 找灵感（search_projects+find_reference_cases+search_github_projects 三路并用）/ 外部项目无交接包（知颜自行整理）/ 想找前辈（find_mentors）；工具清单 +2 行（开放资源与前辈连接）
- **技能图谱大全**（需8）：/api/skills 每技能挂可参与项目列表（stage_label 映射五季，最多 8 个按 id 排序），扩至 24 技能；前端改名 + 行可点击弹窗（项目列表含阶段徽章 / 无项目时"适合发起新项目"空态）
- **功能详情弹窗**（需7）：个人/校园双板块 8 个功能项全部可点击（FEATURE_DETAILS 8 项：档案卡 / 续种清单 / 灵感对接 / 前辈连接 / 种子库 / 交接包实探 / 六维匹配 / 唤醒邀约），detail-modal 通用弹窗（图标/标题/副题/正文/试一试提示）
- **昵称前置投票**（需8/需9）：askNickname Promise 化弹窗（nick-modal，Enter/Escape 支持，localStorage fs_nick 记忆），投票先确认昵称再 fetch /api/votes——票数按昵称分开统计、一人一票防刷；建档发生在对话中由知颜问询（upsert_user_profile nickname 必填），故事点赞为本地轻量操作不在此列
- **南大专属种子卡**（需6/需10）：档案墙新增「南京大学 · 传承实录」区块——3 张专属种子卡（nju-card：种子图标 / 数字事实条 26届·436人·7万+ / 专属种子卡界面 项目方向·已解决·可复用 / 真实报道链接），数据与库内项目 20/21/22 一致
- **修复弹窗遮挡缺陷**：display:flex 覆盖 hidden 默认样式导致遮罩永久拦截整页点击——补 `.detail-modal[hidden], .nick-modal[hidden] { display:none }`
- 验证：py_compile 通过；Playwright 8/8（南大 3 卡 / 种子卡界面 / 图谱改名 24 行 / 技能弹窗 5 项目 / 双板块功能弹窗 / 投票昵称弹窗 + 提交关闭）；SSE 实测意图分流全链路（建档→项目检索→GitHub 检索→find_mentors，推荐带解释与行动建议）；/api/handover 9 份五件套计数正常

### v6.0 · 评审反馈响应：真实试点 + 交接包实探 + 六维匹配（2026-09-17）
针对评审四项意见（真实试点 / 完整交接包展示 / 真实效果 / 匹配有效性）的系统性升级：
- **六维可解释匹配**（project_tools.py）：score_project_match 从四维升级为六维——技能互补 40 + 兴趣与议题 25 + **年级阶梯 10**（_GRADE_LADDER 常量；大一 10/大二 9/大三 6/大四 3/研一 8/研二 5/研三 2，临近毕业降档并提示）+ 传承准备度 10 + **社交邻近 8**（领域标签交集）+ 时间投入 7；修复归一化 known_weight（时间投入按 7 计）；新增 confirmation_flow 三步确认（接棒意愿→原负责人核验授权→双方确认后唤醒）；match_policy 与 sp（11,400+ 字）同步六维口径
- **修复 grade 查询缺陷**：search_projects 匹配时 fs_users select 列漏 grade，导致年级阶梯恒为"未知不补分"——已修复，六维全部生效（SSE 实测回复含"年级阶梯 10/10"）
- **交接包实探**（web_server.py + 前端）：新增 `/api/handover` 接口（overview 含项目标题/阶段/五件套计数；detail 返回全文+实时 readiness 评估）；前端新增「交接包实探」区块（列表点击直读五件套与治理三声明原文）；`/api/evidence` pilot 升级为真实试点实录（两例 cases：接棒人/六维分/票数/readiness/唤醒时间，全部库表实时聚合）
- **两例真实续种试点**（scripts/run_pilot_transfer.py，9/9 步全绿，走生产工具 .func 与校验逻辑，零模拟数据）：
  - 试点 A：项目17「南雍机位图鉴」摄影学长→大一新人**林小满**（user_id 36）：建档→六维匹配 72/100→投票→三步确认→唤醒（stage=fifth，owner 变更）
  - 试点 B：项目15「衣旧情深」毕业班主力→大二新人**陈知夏**（user_id 37）：原负责人补交交接包（治理三声明强校验，package_id=8）→建档→六维匹配 61/100→投票→唤醒（stage=fifth）
  - 匹配留痕：两例六维快照写入 fs_match_logs（72/61 分含逐维证据）；唤醒记录+传承故事卡落库
- **数据治理**：项目9/10/11 旧格式交接包（分号纯文本）规范化为 JSON 数组；删除项目1重复旧包×2；治理声明去重（项目15/17）；交接包现存 6 份全部有真实内容
- **纯函数测试**：test_explainable_match.py 重写 4 用例（六维已知证据/未知维度披露/年级阶梯奖惩/确认流程存在）全绿；pure_function_loader 升级支持模块级常量提取（修 NameError）
- 验证：py_compile 通过；/api/evidence、/api/handover（overview+detail）实测正常；SSE 对话流实测六维匹配完整解释（含年级阶梯生效）；Playwright 验证试点实录 2 卡渲染、交接包列表 6 项、项目17 详情五件套+治理三声明、无 JS 错误
- 已知问题：test_run 沙箱偶发 LLM 流式工具参数分片丢失（空参数 {} 调用），真实 SSE 部署链路无此问题（多轮实测正常）


### v5.0–v5.2 · 决赛增强（2026-09-17，来自用户上传包合并）
- **v5.0 验证中心**：新增 `/api/evidence` 实时证据接口与前端「验证中心」区块（EVIDENCE, NOT PROMISES）；匹配升级为可审计四维评分 `score_project_match`（命中证据、能力缺口、不确定性、决策边界）；补充真实跨届试点方案（docs/真实试点方案.md，含指标口径与授权/有效期/权益规则）
- **v5.1 接续治理闭环**：授权范围、资源有效期、原团队权益升级为交接包强校验；新增 100 分接续准备度 `assess_transfer_readiness`（五件套 50 + 动态 20 + 治理声明 30），正式唤醒前阻断缺项
- **v5.2 决赛交付**：接棒时资源到期校验及异常日期测试；7 页终审答辩 PPT、20 问 QA 逐字稿（DOCX/DOC）
- **配套脚本**：pure_function_loader（无数据库纯函数加载）+ 三个测试（可解释匹配/检索兜底/接续准备度）+ 四个构建脚本（PPT/QA文档/视频/打包）
- 决赛材料存于 `决赛材料/` 目录；README 同步
- 注意：本次合并未连接生产库重新部署，新增接口需部署后联调；PPT 中 80% 资料可用率等属试点目标非实测



### v4.5 · 部署链接交付（2026-09-15）
- 确定项目访问域名并全链路验证：https://e172394c-11db-4a35-8ab0-0567ecbffed7.dev.coze.site/（首页 200 / 对话页 200 / 静态资源 200 / SSE 对话流实测正常，知颜人格回复验证通过）
- 项目文档回填体验入口链接，升级 v1.3（14 页）；本地 PDF 两份副本同步更新，对象存储直传版经回读校验（1,192,927 bytes / 14 页 / 链接在文内）
- 注意：正式生产部署仍需用户在 IDE 点击「部署」按钮；若产出新链接需同步替换文档


### v4.4 · 用户上传快照合并（2026-09-15）
合并用户上传的 `第五个季节(1).zip`（基于 v4.2/v4.3 之后的更新版本，7 个文件）：
- **检索兜底**（project_tools.py）：search_projects 三级匹配——精确命中（exact）→ 同义主题召回（related，_query_terms/_related_score 打分）→ 近期真实项目探索（explore），杜绝"没有相关项目"一句话结束对话
- **检索护栏**（agents/agent.py）：system_prompt 追加 retrieval_guardrail——related 模式必须说明"相邻在哪里"，严禁把相邻推荐包装成精确匹配
- **对话页引导面板**（app.js/index.html/style.css）：欢迎语重写 + 新增 3 张起始卡片（找适合我的项目 / 把想法变成项目 / 把项目交给下一届）；快捷体验区标签改为「核心旅程」「更多能力」；支持 ?view=chat URL 直达
- **示范种子脚本**（scripts/seed_showcase_projects.py）：幂等补充多领域演示项目（按标题判重、只增不删），README 附使用说明
- README.md 同步 26 工具 / 14 表
- 验证：py_compile 通过、26 工具完整、相邻推荐实测生效（音乐查询→命中休眠音乐节种子）、引导面板 3 卡渲染、hero 12 粒子保留、无 JS 错误无横向溢出


### v4.3 · 提交材料包（2026-09-15）
- 项目文档升级至 v1.1（对应系统 v4.2）：新增 4.6 真实案例库、4.7 显式推理链与人格两个创新点；功能地图补 D 节「需求推理与成长规划」；架构图更新 26 工具/14 表/sp 约 11,300 字；效果验证补推理实测与 Playwright 断言；附录同步；目录页码按实测回填（总 14 页）
- 新增《视频脚本.md》：3 分 30 秒分镜脚本（片头/痛点/概念/四段功能演示/技术亮点/结语）+ 配音与录制清单；含 njubox 命名规范「团队名-第五季·续种」
- 两份 PDF 均上传对象存储（预签名 URL 24h 有效，见对话交付记录）；本地副本：docs/项目文档.pdf、docs/视频脚本.md

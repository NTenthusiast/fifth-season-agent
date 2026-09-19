# 第五季 · 续种

**校园未竟梦想的 AI 传承智能体** ｜ 南京大学 · 2026 EL 大赛 AI 智能体创新专项组参赛作品

---

## 这是什么

校园里每年都有大量因毕业、换届、时间不足而暂停的好项目——公益服务、文化记录、工具开发、社团活动。
它们往往不是失败了，只是**没人接得住**。

「第五季·续种」让 AI 智能体**知颜**接管这些项目的传承生命周期：

```
春·萌芽（建档立项） → 夏·生长（组队执行） → 秋·沉淀（交接包）
→ 冬·蛰伏（休眠归档） → 第五季·重生（唤醒接棒）
```

一到四季是项目的一生，**第五季**是那个让循环重新开始的力量——
让每一份被时间搁置的校园善意，都能等到接过它的人。

## 核心能力

| 板块 | 能力 |
|---|---|
| 四季之旅 | 种子卡建档、能力互补组队（申请—审批制）、交接包五件套提炼、休眠归档、三层叙事唤醒接棒 |
| 传承宝库 | 传承故事墙、毕业季托付书（PNG）、种子卡分享海报（PNG）、项目健康巡检、全校技能图谱、需求投票唤醒、传承者成就、跨项目协作发现 |
| 个人板块 | 档案画像、待办管理、灵感库、校园议题洞察 |

智能体共挂载 **26 个工具**，全部读写真实数据库，不编造数据。

## 技术架构

| 层 | 技术 |
|---|---|
| Agent 框架 | LangChain `create_agent` + LangGraph，滑动窗口记忆（40 条，含工具调用配对保护） |
| 大模型 | doubao-seed-2-0-pro，经平台网关流式输出 |
| Web 服务 | FastAPI，SSE 流式对话 + 11 个 REST 端点 |
| 数据库 | 平台 Supabase PostgreSQL，14 张业务表，开发/生产双库隔离 |
| 对象存储 | S3 兼容（coze_coding_dev_sdk），托付书/海报产物 |
| 图像生成 | Pillow 服务端渲染 |
| 前端 | 原生 HTML/CSS/JS，零依赖 |

## 目录结构

```
src/agents/agent.py            Agent 主逻辑（模型装配 / 记忆窗口 / 工具异常兜底）
src/tools/                     26 个工具：personal_tools / project_tools / legacy_tools
src/storage/database/          Supabase 客户端（含 503 重试与客户端复用）
src/storage/memory/            LangGraph checkpointer（Postgres，含连接重试）
src/web_server.py              FastAPI 路由：SSE 对话 + 故事墙/图谱/投票/排行等 REST
src/main.py                    服务入口（平台标准 GraphService）
config/agent_llm_config.json   模型参数 + 系统提示词 + 工具清单
assets/web/                    前端（index.html / style.css / app.js）
docs/                          参赛项目文档
AGENT.md                       项目档案与变更日志
```

## 本地运行

### 方式一：启动完整服务（推荐）

```bash
bash scripts/http_run.sh -m http -p 5000
```

启动后浏览器打开 <http://localhost:5000/> 即可看到介绍页与对话页。

> ⚠️ **请勿直接双击 `assets/web/index.html` 打开。**
> 页面通过 `/static/...` 引用样式与脚本，由 FastAPI 挂载 `assets/web/` 目录提供；
> 以 `file://` 方式直接打开会导致样式与脚本全部 404，页面无法正常显示。

### 方式二：仅本地调试图（不带后端）

```bash
bash scripts/local_run.sh -m flow                  # 跑一遍完整流程
bash scripts/local_run.sh -m node -n <node_name>   # 单节点调试
```

### 环境变量

服务依赖平台注入的以下变量（沙箱内自动就绪）：

```
COZE_INTEGRATION_MODEL_BASE_URL   模型网关地址
COZE_WORKLOAD_IDENTITY_API_KEY    工作负载身份密钥
COZE_SUPABASE_URL / COZE_SUPABASE_ANON_KEY / COZE_SUPABASE_SERVICE_ROLE_KEY
COZE_BUCKET_ENDPOINT_URL / COZE_BUCKET_NAME
```

## 使用示例

进入对话页后，先用一句话介绍自己：

> 我是大二的小林，计算机专业，会前端和摄影，想找点对校园有用的事做。

知颜会为你建档，并在后续对话中完成建项目、找伙伴、写交接包、休眠与唤醒的全过程。

页面底部另备有 **四季之旅** 与 **传承宝库** 两组快捷指令，可直接点击体验各项能力。

## 演示库补充

若部署库中的项目方向较少，可在 Coze 项目终端执行以下幂等脚本。它只新增缺失的示范种子，按标题判重，不覆盖或删除真实用户数据：

```bash
python scripts/seed_showcase_projects.py
```

脚本覆盖心理健康、公益、环保、无障碍、校园文化、学习支持、职业发展、运动、动物保护、国际交流等方向，并为休眠项目补齐可演示的交接包。

## 验证边界与真实试点

首页“验证中心”通过 `/api/evidence` 实时聚合项目档案、交接包覆盖、唤醒记录和故事记录。这里的数字是系统运行证据，不被表述为长期传承成效。跨届有效性仍需真实社团在连续周期中验证，指标、授权边界与复盘方法见 [真实试点方案](docs/真实试点方案.md)。

可解释匹配采用“技能互补 40% + 兴趣与议题 35% + 传承准备度 15% + 时间投入 10%”。未知维度不臆测补分，并返回命中证据、能力缺口和决策边界；推荐分不自动决定入组或接棒。

交接包不再只保存经验文本：系统强制记录授权范围、资源有效期与原团队权益，并在正式唤醒前计算接续准备度。五件套、过程动态和三项治理声明均通过后才允许接棒，避免“资料存在但不可用、可见但未获授权”。

---

*春日提出，夏日行动，秋日沉淀，冬日守望；待到第五季，让未完成的美好重新发生。*

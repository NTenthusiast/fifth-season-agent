"""「第五季·续种」——校园未竟梦想的 AI 传承智能体

主逻辑：LangGraph Agent 编排个人板块与校园板块工具，
以四季状态机（春/夏/秋/冬/第五季）驱动校园项目的全生命周期传承。
"""

import json
import logging
import os
from typing import Annotated

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage

from storage.memory.memory_saver import get_memory_saver
from tools import ALL_TOOLS

logger = logging.getLogger("fifth_season.agent")

LLM_CONFIG = "config/agent_llm_config.json"

# 默认保留最近 20 轮对话 (40 条消息)
MAX_MESSAGES = 40


def _windowed_messages(old, new):
    """滑动窗口: 只保留最近 MAX_MESSAGES 条消息。

    直接切片有一个致命副作用：若正好把 AIMessage(tool_calls) 切掉、而它的
    ToolMessage 留在窗口首部，上游 OpenAI 兼容网关会以
    「messages with role 'tool' must be a response to a preceding message with
    'tool_calls'」直接返回 400。每回合新增 2~4 条消息，40 条边界迟早会被撞上。
    因此切片后必须把首部孤立的工具结果一并丢弃，落到安全边界上。
    """
    messages = add_messages(old, new)[-MAX_MESSAGES:]  # type: ignore
    # 首部若为工具结果，说明其 AIMessage(tool_calls) 已被切掉 → 继续向后跳过
    start = 0
    while start < len(messages) and isinstance(messages[start], ToolMessage):
        start += 1
    trimmed = messages[start:]
    # 极端情况下窗口内全是工具结果，宁可不裁剪也不能产生非法消息序列
    return trimmed or messages


class AgentState(MessagesState):
    messages: Annotated[list[AnyMessage], _windowed_messages]


# 数据库/网关临时性故障的特征。只保留「能确定是记忆库本身出问题」的信号：
# 此前把 "connection" / "timeout" / "503" 这类过宽关键词也算进来，导致一次普通的
# 工具报错（如对象存储超时）就会被判定为记忆库故障，进而触发「严禁再调用任何
# 数据库类工具」的话术，让知颜在正常场景下忽然说"记忆库在打盹"——这是"显得蠢"
# 的直接来源之一，故收窄判据。
_DB_FAULT_KEYWORDS = (
    "PGRST002",                     # Supabase schema cache 未就绪
    "schema cache",
    "Missing response",
    "PoolTimeout",                  # 连接池耗尽
    "couldn't get a connection",
    "connection is bad",
    "Network is unreachable",
    "检索项目失败", "检索用户失败", "查询用户失败", "查询项目失败",
    "查询失败", "检索失败", "统计技能图谱失败", "巡检失败", "建档失败",
)

_DB_FAULT_GUIDANCE = (
    "【记忆库连接异常：平台数据库网关临时故障，与用户输入无关】\n"
    "请按以下方式回应：\n"
    "1. 平实说明记忆库暂时连不上，不要用撒娇或卖萌的措辞。"
    "示例：「记忆库暂时连不上，建档先搁一搁。你可以先说说想做什么方向，恢复了我就补上。」\n"
    "2. 本次回复不要重试同一个工具；可以先了解用户的专业、技能、兴趣与想接棒的方向，"
    "为恢复后的匹配推荐做准备；\n"
    "3. 告诉用户稍等几分钟再试即可，无需刷新或退出。"
)


def _is_db_fault(exc: Exception) -> bool:
    text = str(exc)
    return any(kw in text for kw in _DB_FAULT_KEYWORDS)


class ToolErrorMiddleware(AgentMiddleware):
    """兜底工具执行异常，避免阻塞 Agent 循环（同步/异步双实现）"""

    def _error_message(self, request, exc) -> ToolMessage:
        if _is_db_fault(exc):
            content = _DB_FAULT_GUIDANCE
        else:
            content = (
                f"工具执行异常，请检查输入后重试或换种方式完成。({exc})"
            )
        return ToolMessage(
            content=content,
            tool_call_id=request.tool_call["id"],
        )

    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except Exception as exc:  # noqa: BLE001
            return self._error_message(request, exc)

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception as exc:  # noqa: BLE001
            return self._error_message(request, exc)


def build_agent(ctx=None, use_memory: bool = True):
    """构建「第五季」智能体：模型 + 四季人格化提示词 + 工具编排 + 短期记忆。

    use_memory=False 时构建无 checkpointer 的图（数据库故障时对话降级用）。
    """
    workspace_path = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    config_path = os.path.join(workspace_path, LLM_CONFIG)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 凭据解析（v10.0 修正优先级）：自有 API Key 一旦配置即优先生效——
    # 平台积分耗尽/停用时，只要 .env 配了 FS_LLM_* 或 OPENAI_*，服务照常可用。
    # base_url 与所选 key 配对：FS_LLM_API_KEY→FS_LLM_BASE_URL；OPENAI_API_KEY→OPENAI_BASE_URL；
    # 都未配置时回落平台网关。
    fs_key = os.getenv("FS_LLM_API_KEY") or ""
    oa_key = os.getenv("OPENAI_API_KEY") or ""
    if fs_key:
        api_key = fs_key
        base_url = os.getenv("FS_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")
    elif oa_key:
        api_key = oa_key
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")
    else:
        api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
        base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")

    conf = cfg.get("config", {})
    # 配置键名是 thinking_type；此前代码读的是 thinking，键名不匹配 → 该开关从未生效。
    thinking_on = conf.get("thinking_type", "disabled") == "enabled"
    extra_body: dict = {"thinking": {"type": "enabled" if thinking_on else "disabled"}}
    if thinking_on and conf.get("reasoning_effort"):
        extra_body["reasoning_effort"] = conf["reasoning_effort"]

    llm = ChatOpenAI(
        model=conf.get("model"),
        api_key=api_key,
        base_url=base_url,
        temperature=conf.get("temperature", 0.4),
        top_p=conf.get("top_p", 0.9),
        # 以下两项此前从未传给模型，配置形同虚设
        max_tokens=conf.get("max_tokens", 4096),
        frequency_penalty=conf.get("frequency_penalty", 0),
        streaming=True,
        timeout=conf.get("timeout", 600),
        extra_body=extra_body,
    )

    logger.info(
        "[agent] llm model=%s temperature=%s thinking=%s max_tokens=%s tools=%d",
        conf.get("model"), conf.get("temperature"),
        extra_body["thinking"]["type"], conf.get("max_tokens"), len(ALL_TOOLS),
    )

    retrieval_guardrail = """

# 零结果兜底（高优先级）
search_projects 返回 match_mode=related 时，必须明确说明“没有完全命中，但找到这些相邻方向”，
并解释每个项目与用户需求相邻在哪里。返回 match_mode=explore 时，先诚实说明没有精确或同义主题命中，
再展示最多 3 个近期真实项目，追问用户愿意拓宽议题、技能还是投入时间。严禁只用一句“没有相关项目”结束对话，
也严禁把相邻推荐包装成精确匹配。
"""

    return create_agent(
        model=llm,
        system_prompt=(cfg.get("sp") or "") + retrieval_guardrail,
        tools=ALL_TOOLS,
        middleware=[ToolErrorMiddleware()],
        checkpointer=get_memory_saver() if use_memory else None,
        state_schema=AgentState,
    )

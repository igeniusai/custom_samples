import os
from datetime import UTC, datetime

from langchain.agents import create_agent
from langchain.tools import BaseTool
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from domyn_agents.integrations.langgraph import input_mapper
from domyn_agents.integrations.langgraph.domyn_platform import (
    PlatformToolRegistry,
    _default_relay,
    get_platform_tools,
)

_platform_tools: PlatformToolRegistry | None = None
if (
    (api_key := os.environ.get("DOMYN_API_KEY"))
    and (space_id := os.environ.get("DOMYN_SPACE_ID"))
    and (channel_id := os.environ.get("DOMYN_CHANNEL_ID"))
    and (base_url := os.environ.get("DOMYN_BASE_URL"))
):
    try:
        _platform_tools = get_platform_tools(
            api_key=api_key,
            space_id=space_id,
            channel_id=channel_id,
            base_url=base_url,
            relay=_default_relay,
        )
        print(f"Loaded platform tools: {_platform_tools}")
    except Exception as exc:
        print(f"Failed to load platform tools: {exc}")

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


@tool
def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers together."""
    return a * b


@tool
def get_current_time() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


@tool
def reverse_string(text: str) -> str:
    """Reverse a string."""
    return text[::-1]


@tool
def count_words(text: str) -> int:
    """Count the number of words in a string."""
    return len(text.split())


LOCAL_TOOLS = [
    add_numbers,
    multiply_numbers,
    get_current_time,
    reverse_string,
    count_words,
    _platform_tools.get_tool("web_search") if _platform_tools else None,
    # _platform_tools.get_tool("show_store_content") if _platform_tools else None,
]

# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def _get_llm() -> ChatOpenAI:
    api_key = os.getenv("VLLM_API_KEY") or os.getenv("VLLM_API_KEY_DEFAULT")
    if not api_key:
        raise RuntimeError("Set VLLM_API_KEY or VLLM_API_KEY_DEFAULT in your .env")

    def _get_api_key():
        return api_key

    return ChatOpenAI(
        model=os.getenv("VLLM_MODEL", "Qwen/Qwen3-32B"),
        api_key=_get_api_key,
        base_url=os.getenv("VLLM_BASE_URL", "https://gateway-dev.llm.crystal.ai/v1"),
        temperature=0.7,
        max_completion_tokens=4000,
    )


@input_mapper(lambda d: {"messages": [{"role": "user", "content": d.get("task", "")}]})
def build_graph(tools: list[BaseTool] | None = None):
    """Build a ReAct agent graph with the given tools (defaults to LOCAL_TOOLS)."""
    filtered_tools = [tool for tool in (tools or LOCAL_TOOLS) if tool is not None]
    return create_agent(_get_llm(), filtered_tools)


graph = build_graph()
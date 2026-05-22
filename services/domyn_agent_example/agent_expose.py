import os
from datetime import UTC, datetime

from domyn_agents.agents.agent import Agent
from domyn_agents.core.decorators import tool
from domyn_agents.llm.openai import OpenAIProvider

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


def _get_llm() -> OpenAIProvider:
    api_key = os.getenv("VLLM_API_KEY") or os.getenv("VLLM_API_KEY_DEFAULT", "")
    base_url = os.getenv("VLLM_BASE_URL", "https://gateway-dev.llm.crystal.ai/v1")
    # OpenAIProvider needs the full completions endpoint; accept base-URL style too.
    if not base_url.endswith("/chat/completions"):
        base_url = base_url.rstrip("/") + "/chat/completions"
    return OpenAIProvider(
        model_name=os.getenv("VLLM_MODEL", "Qwen/Qwen3-32B"),
        url=base_url,
        api_key=api_key,
        generation_params={
            "temperature": 0.7,
            "max_completion_tokens": 4000,
        },
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(name="add_numbers", description="Add two numbers together.")
def add_numbers(a: float, b: float) -> float:
    return a + b


@tool(name="multiply_numbers", description="Multiply two numbers together.")
def multiply_numbers(a: float, b: float) -> float:
    return a * b


@tool(name="get_current_time", description="Return the current UTC time as an ISO 8601 string.")
def get_current_time() -> str:
    return datetime.now(UTC).isoformat()


@tool(name="reverse_string", description="Reverse a string.")
def reverse_string(text: str) -> str:
    return text[::-1]


@tool(name="count_words", description="Count the number of words in a string.")
def count_words(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

agent = Agent(
    name="DomynAgent",
    description="A helpful ReAct agent that can perform arithmetic, string operations, and tell the time.",
    instruction=(
        "You are a helpful assistant. Use the available tools to answer the user's request. "
        "If the user updates tool parameters mid-conversation, continue with the new values."
    ),
    llm_provider=_get_llm(),
    tools=[add_numbers, multiply_numbers, get_current_time, reverse_string, count_words],
)

import os
from datetime import UTC, datetime

from domyn_agents.agents.agent import Agent
from domyn_agents.core.decorators import tool
from domyn_agents.llm.openai import OpenAIProvider
from domyn_agents.planner_strategy.context_management.full_messages import FullMessageContext
from domyn_agents.planner_strategy.prompting.structural_tags_prompting import (
    StructuralTagMessagePrompting,
)
from domyn_agents.planner_strategy.react import ReactPlannerStrategy

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


def _get_planner_with_stop() -> ReactPlannerStrategy:
    return ReactPlannerStrategy(
        use_stop=True,
        context_manager=FullMessageContext(
            prompting=StructuralTagMessagePrompting(),
            narrow_non_visible_agents=True,
            name="subagent_full_message_context",
        ),
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

math_agent = Agent(
    name="MathAgent",
    description="Specialist agent for arithmetic operations (addition, multiplication).",
    instruction=(
        "You are a math specialist. Use the available arithmetic tools to "
        "compute the requested result and return it concisely."
    ),
    llm_provider=_get_llm(),
    tools=[add_numbers, multiply_numbers],
    planner=_get_planner_with_stop(),
)

string_agent = Agent(
    name="StringAgent",
    description="Specialist agent for string operations (reverse, word count).",
    instruction=(
        "You are a string-processing specialist. Use the available tools to "
        "transform or analyze the input text and return the result concisely."
    ),
    llm_provider=_get_llm(),
    tools=[reverse_string, count_words],
    planner=_get_planner_with_stop(),
)

agent = Agent(
    name="DomynAgent",
    description=(
        "Orchestrator agent. Delegates arithmetic to MathAgent and string "
        "operations to StringAgent; answers time-related questions directly."
    ),
    instruction=(
        "You are an orchestrator. For arithmetic questions delegate to "
        "MathAgent. For string operations delegate to StringAgent. For "
        "time-related questions, use the get_current_time tool yourself. "
        "If the user updates tool parameters mid-conversation, continue "
        "with the new values."
    ),
    llm_provider=_get_llm(),
    tools=[get_current_time],
    sub_agents=[math_agent, string_agent],
)

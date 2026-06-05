"""Quick local test — runs the agent directly without the WebSocket relay.

Usage:
    python test_local.py
    python test_local.py "Add 5 and 7"
"""

import asyncio
import sys

from agent_expose import agent
from domyn_agents.core import BaseEvent, ExecutionEventType
from domyn_agents.runner import Runner

CASES = [
    "Add 5 and 7",
    "Multiply 3 by 9",
    "What time is it?",
    "Reverse the string 'hello world'",
    "Count the words in: the quick brown fox",
]


async def run(task: str) -> None:
    print(f"\nTask: {task!r}")
    print("-" * 60)

    user_input = BaseEvent(
        event_type=ExecutionEventType.USER_INPUT,
        author="user",
        content=[],
    )
    # Inject task text via metadata so Runner builds correct user context
    from domyn_agents.core import Part

    user_input = user_input.model_copy(update={"content": [Part(text=task)]})

    runner = Runner()
    async for event in runner.run(
        application_name="test",
        user_id="local-tester",
        user_input=user_input,
        root=agent,
    ):
        if event.event_type == ExecutionEventType.RESPONSE and not event.is_partial:
            text = " ".join(p.text for p in (event.content or []) if p.text)
            if text:
                print(text)
        elif event.event_type == ExecutionEventType.TOOL_START:
            action = event.action
            name = getattr(action, "name", "?") if action else "?"
            params = getattr(action, "parameters", {}) if action else {}
            print(f"  [tool] {name}({params})")

    print("-" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(run(" ".join(sys.argv[1:])))
    else:
        for case in CASES:
            asyncio.run(run(case))

"""Quick local test — invokes the graph directly without the WebSocket relay.

Usage:
    python test_local.py
    python test_local.py "Add 5 and 7"
"""

import sys
from agent_expose import graph

CASES = [
    "Add 5 and 7",
    "Multiply 3 by 9",
    "What time is it?",
    "Reverse the string 'hello world'",
    "Count the words in: the quick brown fox",
]


def run(task: str) -> None:
    print(f"\nTask: {task!r}")
    print("-" * 60)
    result = graph.invoke({"messages": [{"role": "user", "content": task}]})
    messages = result.get("messages", [])
    if messages:
        print(messages[-1].content)
    print("-" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run(" ".join(sys.argv[1:]))
    else:
        for case in CASES:
            run(case)

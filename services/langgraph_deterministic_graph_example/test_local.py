"""Quick local test — invokes the graph directly without the WebSocket relay.

Usage:
    python test_local.py
    python test_local.py "salary=90000 loan=300000 term=30 credit_score=750 monthly_debt=200"
"""

import sys
from loan_assessment_graph import _EMPTY_STATE, graph

CASES = [
    "salary=70000 loan=250000 term=30 credit_score=720 monthly_debt=400",
    "salary=15000 loan=100000 term=30 credit_score=700 monthly_debt=0",
    "salary=60000 loan=500000 term=30 credit_score=550 monthly_debt=800",
    "salary=80000 loan=200000 term=15 credit_score=800 monthly_debt=0",
]


def run(input_text: str) -> None:
    print(f"\nInput: {input_text!r}")
    print("-" * 60)
    # When calling the graph directly (outside the relay), pass the full initial state.
    # The input_mapper handles {"task": ...} conversion automatically when connected via domyn expose.
    initial = {**_EMPTY_STATE, "raw_input": input_text}
    result = graph.invoke(initial)
    print(result["result"])
    print("-" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run(" ".join(sys.argv[1:]))
    else:
        for case in CASES:
            run(case)

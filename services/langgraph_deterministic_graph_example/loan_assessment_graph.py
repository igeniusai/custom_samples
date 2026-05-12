"""Deterministic loan assessment graph — Domyn platform blueprint.

Flow:
    START → parse_input → validate_income → calculate_dti
          → assess_risk → make_decision → format_result → END

    On parse failure:
    START → parse_input → END  (with a structured error explaining what to fix)

Input
-----
Must be called by passing a JSON object string with these required keys:

    {
        "salary":       <number>  — annual salary in dollars (e.g. 45000),
        "loan_amount":  <number>  — requested loan in dollars (e.g. 30000),
        "term_years":   <integer> — loan term in years (e.g. 25),
        "credit_score": <integer> — applicant credit score (e.g. 750),
        "monthly_debt": <number>  — existing monthly debt in dollars (e.g. 500)
    }

If the JSON is malformed, a key is missing, or a value cannot be coerced to
the expected numeric type, the graph exits immediately with a plain-English
error message that lists the missing/invalid fields and shows a valid example.
The calling agent can read this message and retry with corrected input.

Output
------
Human-readable approval decision streamed back via the relay, e.g.:

    Loan Assessment: APPROVED
      Applicant salary:    $45,000/yr
      Loan requested:      $30,000 over 25 years
      Credit score:        750 (LOW risk)
      Debt-to-income:      18.7%
      Decision reason:     Excellent credit profile.

Customization guide
-------------------
- Add/change assessment rules inside make_decision() and assess_risk().
- Add new fields to LoanState, _REQUIRED_FIELDS, and parse them in parse_input().
- The graph itself (build_graph) stays the same — only node logic changes.
"""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from domyn_agents.integrations.langgraph.utils import input_mapper

_REQUIRED_FIELDS = {
    "salary": "annual salary in dollars (e.g. 45000)",
    "loan_amount": "requested loan amount in dollars (e.g. 30000)",
    "term_years": "loan term in years (e.g. 25)",
    "credit_score": "credit score as an integer (e.g. 750)",
    "monthly_debt": "existing monthly debt obligations in dollars (e.g. 500)",
}

_EXAMPLE = json.dumps({k: v.split(" ")[0].lstrip("(e.g. ").rstrip(")") for k, v in _REQUIRED_FIELDS.items()})


class LoanState(TypedDict):
    raw_input: str
    salary: float
    loan_amount: float
    term_years: int
    credit_score: int
    monthly_debt: float
    dti_ratio: float
    risk_level: str
    approved: bool | None  # None = not yet decided; False = rejected; True = approved
    reason: str
    result: str
    parse_error: bool


# ---------------------------------------------------------------------------
# Nodes — modify these to implement your own lending rules
# ---------------------------------------------------------------------------


def parse_input(state: LoanState) -> LoanState:
    """Parse JSON input; short-circuit with an error result if fields are missing or malformed."""
    raw = state["raw_input"]
    received = f"Received: {raw!r}"

    def _extract_json(text: str) -> dict:
        """Try to parse text as JSON directly, then fall back to extracting the
        outermost {...} substring if the input contains surrounding prose."""
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        # Find the first '{' and the last '}' and try every outermost slice
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start : end + 1]
            result = json.loads(candidate)  # raises if still invalid
            if isinstance(result, dict):
                return result
        raise ValueError("no JSON object found in input")

    try:
        data = _extract_json(raw)
    except Exception as exc:
        return {
            **state,
            "parse_error": True,
            "result": (
                f"PARSE ERROR: could not parse input as JSON ({exc}).\n"
                f"{received}\n"
                f"Please call this tool again with a JSON object containing these fields:\n"
                + "\n".join(f"  {k}: {desc}" for k, desc in _REQUIRED_FIELDS.items())
                + f"\nExample: {_EXAMPLE}"
            ),
        }

    missing = [k for k in _REQUIRED_FIELDS if k not in data]
    if missing:
        return {
            **state,
            "parse_error": True,
            "result": (
                f"PARSE ERROR: missing required fields: {', '.join(missing)}.\n"
                f"{received}\n"
                f"Keys found: {list(data.keys())}\n"
                f"Please call this tool again with a JSON object containing all of these fields:\n"
                + "\n".join(f"  {k}: {desc}" for k, desc in _REQUIRED_FIELDS.items())
                + f"\nExample: {_EXAMPLE}"
            ),
        }

    try:
        return {
            **state,
            "parse_error": False,
            "salary": float(data["salary"]),
            "loan_amount": float(data["loan_amount"]),
            "term_years": int(data["term_years"]),
            "credit_score": int(data["credit_score"]),
            "monthly_debt": float(data["monthly_debt"]),
        }
    except (TypeError, ValueError) as exc:
        return {
            **state,
            "parse_error": True,
            "result": (
                f"PARSE ERROR: invalid field value ({exc}).\n"
                f"{received}\n"
                f"All numeric fields must be numbers, not strings.\n"
                f"Example: {_EXAMPLE}"
            ),
        }


def validate_income(state: LoanState) -> LoanState:
    if state["salary"] < 20_000:
        return {**state, "approved": False, "reason": "Insufficient annual income (minimum $20,000)"}
    return state


def calculate_dti(state: LoanState) -> LoanState:
    """Debt-to-income ratio: (estimated monthly payment + existing debt) / monthly income."""
    monthly_income = state["salary"] / 12
    r = 0.065 / 12  # assumed annual rate 6.5% — adjust to your product rate
    n = state["term_years"] * 12
    if r > 0 and n > 0:
        monthly_payment = state["loan_amount"] * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    else:
        monthly_payment = state["loan_amount"] / n if n else 0

    dti = (monthly_payment + state["monthly_debt"]) / monthly_income if monthly_income else 1.0
    return {**state, "dti_ratio": round(dti, 4)}


def assess_risk(state: LoanState) -> LoanState:
    score = state["credit_score"]
    if score >= 740:
        risk = "low"
    elif score >= 670:
        risk = "medium"
    elif score >= 580:
        risk = "high"
    else:
        risk = "rejected"
    return {**state, "risk_level": risk}


def make_decision(state: LoanState) -> LoanState:
    # Skip if already rejected upstream (e.g. income check)
    if state.get("approved") is False:
        return state

    if state["risk_level"] == "rejected":
        return {
            **state,
            "approved": False,
            "reason": f"Credit score {state['credit_score']} is below minimum threshold (580)",
        }

    if state["dti_ratio"] > 0.43:
        return {
            **state,
            "approved": False,
            "reason": f"Debt-to-income ratio {state['dti_ratio']:.1%} exceeds maximum allowed (43%)",
        }

    risk_notes = {
        "low": "Excellent credit profile.",
        "medium": "Good credit profile; standard terms apply.",
        "high": "Fair credit; higher interest rate may apply.",
    }
    return {**state, "approved": True, "reason": risk_notes[state["risk_level"]]}


def format_result(state: LoanState) -> LoanState:
    status = "APPROVED" if state["approved"] else "DENIED"
    lines = [
        f"Loan Assessment: {status}",
        f"  Applicant salary:    ${state['salary']:,.0f}/yr",
        f"  Loan requested:      ${state['loan_amount']:,.0f} over {state['term_years']} years",
        f"  Credit score:        {state['credit_score']} ({state['risk_level'].upper()} risk)",
        f"  Debt-to-income:      {state['dti_ratio']:.1%}",
        f"  Decision reason:     {state['reason']}",
    ]
    return {**state, "result": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Graph assembly — you should not need to modify anything below this line
# ---------------------------------------------------------------------------

def _route_after_parse(state: LoanState) -> str:
    return END if state["parse_error"] else "validate_income"


_EMPTY_STATE = LoanState(
    raw_input="",
    salary=0,
    loan_amount=0,
    term_years=30,
    credit_score=0,
    monthly_debt=0,
    dti_ratio=0.0,
    risk_level="",
    approved=None,
    reason="",
    result="",
    parse_error=False,
)


@input_mapper(lambda d: {**_EMPTY_STATE, "raw_input": d.get("task", "")})
def build_graph():
    builder: StateGraph = StateGraph(LoanState)
    builder.add_node("parse_input", parse_input)
    builder.add_node("validate_income", validate_income)
    builder.add_node("calculate_dti", calculate_dti)
    builder.add_node("assess_risk", assess_risk)
    builder.add_node("make_decision", make_decision)
    builder.add_node("format_result", format_result)

    builder.add_edge(START, "parse_input")
    builder.add_conditional_edges("parse_input", _route_after_parse)
    builder.add_edge("validate_income", "calculate_dti")
    builder.add_edge("calculate_dti", "assess_risk")
    builder.add_edge("assess_risk", "make_decision")
    builder.add_edge("make_decision", "format_result")
    builder.add_edge("format_result", END)

    return builder.compile()


graph = build_graph()

"""
LLM-based content-safety judge.

Pure Python — no FastAPI, no HTTP routing.
Owns the full evaluation pipeline:
  1. Build the LLM prompt.
  2. Call the LLM with retry logic.
  3. Parse and validate the verdict.
  4. Map the verdict to a hook result dict.
"""

import asyncio
import copy
import json
import re
import uuid
from datetime import datetime
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import GuardrailState, JudgeVerdict, Verdict
from app.models import GuardrailRequest

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a content-safety judge for an agentic system. \
Review the provided text and apply the policy below if needed, \
then return a verdict.

POLICY:
```
{policy}
```

You MUST respond with a single JSON object and nothing else — no markdown fences, \
no prose, no explanation outside the JSON. The object must have exactly these fields:

  "thoughts" - your internal reasoning process that lead to the verdict (this will not be shown to the user)
  "verdict"  — one of: "approved", "rejected", "modified"
  "reason"   — one sentence explaining your decision (never quote or repeat content that violates the policy)
  "output"   — if "modified": the corrected text; if "rejected": the message to show the user; if "approved": ""

Example (approved):
{{"verdict": "approved", "reason": "Reason for the verdict", "output": ""}}

Example (rejected):
{{"verdict": "rejected", "reason": "Reason for the verdict", "output": "I cannot help with that request."}}

Example (modified):
{{"verdict": "modified", "reason": "Reason for the verdict", "output": "The cleaned version of the text."}}
"""

_RETRY_PROMPT = (
    "Your previous response could not be parsed. "
    "Return ONLY a raw JSON object — no markdown, no extra text. "
    "Required fields: "
    '"verdict" (exactly one of "approved", "rejected", "modified"), '
    '"reason" (string), '
    '"output" (string). '
    'Example: {{"verdict": "approved", "reason": "Complies with policy.", "output": ""}}'
)

_MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------


async def _call_llm(messages: list[dict[str, str]], state: GuardrailState) -> str:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if state.api_key:
        headers["Authorization"] = f"Bearer {state.api_key}"

    payload: dict[str, Any] = {
        "model": state.model_name,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 8096,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(state.url, headers=headers, json=payload)  # type: ignore[arg-type]
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError(f"LLM returned empty choices: {data}")
        content = choices[0].get("message", {}).get("content")
        if content is None:
            raise ValueError(f"LLM returned null content: {choices[0]}")
        return content


def _extract_json(text: str) -> str:
    """Return the JSON payload from the LLM response.

    Only strip fences if the model wrapped the *entire* response in one —
    never strip fences that appear inside string values (e.g. ```java code
    blocks inside the "output" field of a valid JSON).
    """
    text = text.strip()
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    if text.startswith("```"):
        match = re.match(r"^```(?:json)?\s*\n?([\s\S]*?)\n?```\s*$", text)
        if match:
            return match.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        return brace.group(0)
    return text


async def _generate_verdict(
    messages: list[dict[str, str]], state: GuardrailState
) -> JudgeVerdict:
    history = list(messages)
    last_error: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        content: str = ""
        try:
            content = await _call_llm(history, state)
            return JudgeVerdict.model_validate_json(_extract_json(content))
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code
            snippet = exc.response.text[:200]
            print(
                f"[judge] attempt {attempt}/{_MAX_RETRIES} LLM returned HTTP {status}: {snippet}"
            )
            if status < 500:
                raise
            await asyncio.sleep(1.0 * attempt)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            print(
                f"[judge] attempt {attempt}/{_MAX_RETRIES} malformed output: {exc}\nRaw: {content!r}"
            )
            history = [
                *history,
                {"role": "assistant", "content": content},
                {"role": "user", "content": _RETRY_PROMPT},
            ]

    raise RuntimeError(
        f"Guardrail failed after {_MAX_RETRIES} attempts"
    ) from last_error


# ---------------------------------------------------------------------------
# Hook result builders
# ---------------------------------------------------------------------------


def _make_hook_result(
    modified_event: dict[str, Any], passed: bool, reason: str, guardrail_name: str
) -> dict[str, Any]:
    display_name = (
        "Input Guardrail Result"
        if guardrail_name == "input_guardrail"
        else "Output Guardrail Result"
    )
    return {
        "modified_event": modified_event,
        "emitted_content": {
            "name": display_name,
            "passed": passed,
            "reason": reason,
        },
    }


def make_hook_error(error_code: str, error_message: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": {"error_code": error_code, "error_message": error_message},
        "emitted_content": {
            "name": "Guardrail Error",
            "passed": False,
            "error_occurred": True,
            "reason": error_message,
        },
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _record_verdict(
    verdict: JudgeVerdict,
    turn_id: Any,
    state: GuardrailState,
    guardrail_name: str,
    label: str,
) -> None:
    verdict.label = label
    if turn_id is not None:
        state.verdict_history.setdefault(str(turn_id), []).append(verdict)
    else:
        print(f"[judge] {guardrail_name} {label} verdict NOT saved — turn_id is None")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def evaluate(
    body: GuardrailRequest,
    state: GuardrailState,
    guardrail_name: str,
) -> dict[str, Any]:
    """
    Evaluate a single event against the guardrail policy.

    Checks are applied in order:
      1. event["action"]["thought"]  — if present
      2. event["content"]            — if present and non-empty; skipped when (1) is rejected

    Returns a hook result dict ready to be returned by a FastAPI endpoint.
    """
    event = body.current_event

    if not state.model_name or not state.url:
        msg = (
            f"LLM provider not configured for {guardrail_name}: "
            "model_name and url are required. Use the admin UI to set them."
        )
        print(f"[judge] {guardrail_name}: {msg}")
        return make_hook_error("llm_not_configured", msg)

    event_type = event.get("event_type", "event")
    turn_id = event.get("turn_id")
    output_event = copy.deepcopy(event)
    passed = True
    reasons: list[str] = []

    # ------------------------------------------------------------------
    # 1. Thought check
    # ------------------------------------------------------------------
    action = event.get("action", {})
    thought_text = action.get("thought")

    if thought_text:
        thought_messages: list[dict[str, str]] = [
            {"role": "system", "content": _SYSTEM_PROMPT.format(policy=state.policy)},
            {
                "role": "user",
                "content": (
                    f"Judge the following {event_type} thought according to the policy."
                    f"\n\n{thought_text}"
                ),
            },
        ]
        try:
            thought_verdict = await _generate_verdict(thought_messages, state)
            _record_verdict(thought_verdict, turn_id, state, guardrail_name, "thought")
        except httpx.HTTPStatusError as exc:
            msg = f"LLM provider returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            print(f"[judge] {guardrail_name} thought error: {msg}")
            return make_hook_error("llm_http_error", msg)
        except Exception as exc:
            msg = str(exc)
            print(f"[judge] {guardrail_name} thought error: {msg}")
            return make_hook_error("guardrail_error", msg)

        reasons.append(f"thought: {thought_verdict.reason}")

        match thought_verdict.verdict:
            case Verdict.REJECTED:
                output_event["event_type"] = "response"
                output_event["author"] = guardrail_name
                output_event["content"] = [
                    {
                        "text": thought_verdict.output
                        or "Your message was blocked by the system."
                    }
                ]
                output_event["timestamp"] = datetime.now().isoformat()
                output_event["event_id"] = str(uuid.uuid4())
                output_event["is_partial"] = False
                return _make_hook_result(
                    output_event, False, thought_verdict.reason, guardrail_name
                )

            case Verdict.MODIFIED:
                modified_warning = (
                    f"\n\n*[SYSTEM NOTE - {guardrail_name}]: This thought was intentionally modified to comply with policy. "
                    f"This modified version is the one that will be considered from now on.*"
                )
                output_event["action"]["thought"] = (
                    thought_verdict.output + modified_warning
                )
                passed = False
            case Verdict.APPROVED:
                pass  # no change to the event; just record the verdict

    # ------------------------------------------------------------------
    # 2. Content check
    # ------------------------------------------------------------------
    content_parts = event.get("content", [])
    content_text = "\n".join((part.get("text") or "") for part in content_parts)

    if content_parts and content_text.strip():
        content_messages: list[dict[str, str]] = [
            {"role": "system", "content": _SYSTEM_PROMPT.format(policy=state.policy)},
            {
                "role": "user",
                "content": (
                    f"Judge the following {event_type} according to the policy."
                    f"\n\n{content_text}"
                ),
            },
        ]
        try:
            content_verdict = await _generate_verdict(content_messages, state)
            _record_verdict(content_verdict, turn_id, state, guardrail_name, "content")
        except httpx.HTTPStatusError as exc:
            msg = f"LLM provider returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            print(f"[judge] {guardrail_name} content error: {msg}")
            return make_hook_error("llm_http_error", msg)
        except Exception as exc:
            msg = str(exc)
            print(f"[judge] {guardrail_name} content error: {msg}")
            return make_hook_error("guardrail_error", msg)

        reasons.append(f"content: {content_verdict.reason}")

        match content_verdict.verdict:
            case Verdict.REJECTED:
                output_event["event_type"] = "response"
                output_event["author"] = guardrail_name
                output_event["content"] = [
                    {
                        "text": content_verdict.output
                        or "Your message was blocked by the system."
                    }
                ]
                output_event["timestamp"] = datetime.now().isoformat()
                output_event["event_id"] = str(uuid.uuid4())
                output_event["is_partial"] = False
                return _make_hook_result(
                    output_event, False, content_verdict.reason, guardrail_name
                )

            case Verdict.MODIFIED:
                modified_warning = (
                    f"\n\n*[SYSTEM NOTE - {guardrail_name}]: This content was intentionally modified to comply with policy. "
                    f"This modified version is the one that will be considered from now on.*"
                )
                task = content_verdict.output + modified_warning
                output_event["content"] = [{"text": task}]
                if output_event.get("event_type") == "agent_start":
                    output_event["action"]["parameters"] = {"task": task}
                passed = False

    overall_reason = "; ".join(reasons) if reasons else "No content to evaluate."
    return _make_hook_result(output_event, passed, overall_reason, guardrail_name)

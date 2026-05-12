"""
Blueprint: REST Hook — Minimal Documentation Example
=====================================================

Purpose
-------
This file is a minimal, heavily documented example showing how to build a
REST endpoint to implement a guardrail via a ``on_agent_event`` hook.  The actual
"business logic" (email-address detection via regex) is intentionally trivial
so the structural and contractual parts of the hook stand out clearly.

How Domyn invokes a REST hook
-----------------------------
Hooks are configured through the Domyn platform UI.  Once registered, the
runner makes a POST request to the configured URL on every event that belongs
to the agent the hook is attached to.  Your service must respond before the
timeout; the runner will use your response to decide what to do next.

This service exposes two endpoints, matching the two guardrail positions
available in the platform:

``POST /input-guardrail``
    Attach this URL when configuring a guardrail that runs **before the
    answer** (i.e. on user input and agent-start events).  Domyn will POST
    ``user_input`` and ``agent_start`` events here.  ``agent_start`` fires
    on agent handoffs — when an agent delegates to a sub-agent — so this
    endpoint can also intercept the input being passed between agents.

``POST /output-guardrail``
    Attach this URL when configuring a guardrail that runs **after the
    response** (i.e. on agent response events).  Domyn will POST ``response``
    events here.

What you receive — the request body
------------------------------------
Every POST carries a JSON body with two fields:

``current_event`` (object, always present)
    The event that just occurred.  This is a serialised ``BaseEvent`` — the
    same structure you see for each event in the Domyn observability view.
    You can use the observability panel to inspect real event payloads and
    understand exactly what your hook will receive at runtime.

``interaction_history`` (list, may be empty)
    The ordered list of past events in this conversation, newest last.
    Each item has the same shape as ``current_event``.
    Useful when your policy needs context (e.g. multi-turn PII checks).

What you must return — the three response patterns
---------------------------------------------------

1. **Pass-through** — do nothing, let execution continue unchanged
   Return ``modified_event`` set to the *unmodified* original event.
   Include ``emitted_content`` to make the check visible in the
   observability view:

   .. code-block:: json

       {
           "modified_event": { /* original event, unchanged */ },
           "emitted_content": {
               "name": "Name to be shown in the UI for this check",
               "passed": true,
               "reason": "No issues found."
           }
       }


2. **Modify** — alter the event content before it continues
   Return ``modified_event`` with a *changed* ``content`` list.  The
   runner will replace the original event with your modified version and
   continue execution normally.  Use this to redact, sanitise, or
   translate content:

   .. code-block:: json

       {
           "modified_event": {
               /* same shape as the original, but content is changed */
               "event_type": "user_input",
               "content": [{"text": "My email is [REDACTED]"}],
               /* all other fields copied from the original */
           },
           "emitted_content": {
               "name": "Name to be shown in the UI for this check",
               "passed": false,
               "reason": "Email address redacted."
           }
       }

3. **Block (interrupt execution)** — stop the pipeline and return a
   message directly to the user
   Replace ``modified_event`` with a *new* event whose ``event_type`` is
   ``"response"``.  The runner treats this as the final answer for this
   turn; no further agents or tools are invoked, the original (potentially harmful) event is discarded, and the user receives only the content of your response:

   .. code-block:: json

       {
           "modified_event": {
               "event_type": "response",
               "author": "my_hook",
               "content": [{"text": "I cannot help with that request."}],
               "timestamp": "2026-01-01T12:00:00",
               "event_id": "event_<uuid>",
               "is_partial": false,
               "need_feedback": false,
               "metadata": {}
           },
           "emitted_content": {
               "name": "My Hook",
               "passed": false,
               "reason": "Request blocked by policy."
           }
       }

   The key difference from *modify*: the ``event_type`` of the returned
   event is ``"response"``, which signals Domyn to treat it as a terminal
   answer rather than a modified input.

Error response — signal a processing failure
--------------------------------------------
If your hook encounters an unrecoverable error (LLM timeout, DB
unavailable, …) you can return an error object instead of a normal
result.  The runner will surface this as a hook error and will interrupt the execution:

.. code-block:: json

    {
        "error_code": "short_snake_case_code",
        "error_message": "Human-readable description of what went wrong."
    }

Run
---
    pip install fastapi uvicorn pydantic
    uvicorn guardrail_hook_example:app --reload --port 9002
"""

import copy
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Request model — mirrors what Domyn POSTs to this endpoint
# ---------------------------------------------------------------------------


class HookRequest(BaseModel):
    """
    The body of every POST Domyn sends to a REST hook.

    ``current_event``
        The event currently being processed.  Your hook decides whether to
        pass it through, modify it, or replace it with a blocking response.

    ``interaction_history``
        All past events for this conversation, oldest first.  Your hook may
        use this for context-aware checks (e.g. detecting repeated violations).
        It is safe to ignore when your check is stateless.
    """

    current_event: dict[str, Any]
    interaction_history: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Response builders — the three patterns a hook can return
# ---------------------------------------------------------------------------


def pass_through(
    event: dict[str, Any], reason: str = "No issues found."
) -> dict[str, Any]:
    """
    Return the event unchanged.

    Execution continues normally.  ``emitted_content`` is included for
    observability — it makes the check result visible in the Domyn UI.
    """
    return {
        "modified_event": event,
        "emitted_content": {
            "name": "Content Hook",
            "passed": True,
            "reason": reason,
        },
    }


def modify_event(event: dict[str, Any], new_text: str, reason: str) -> dict[str, Any]:
    """
    Return a modified copy of the event.

    The runner replaces the original event with this one and continues
    execution.  Only the ``content`` list is changed here; all other
    event fields (event_id, author, timestamp, …) are preserved so that
    downstream agents still have full context.

    ``passed`` is set to ``False`` to indicate the content was altered —
    the hook *intervened*, even though execution was not stopped.
    """
    modified = copy.deepcopy(event)
    modified["content"] = [{"text": new_text}]

    return {
        "modified_event": modified,
        "emitted_content": {
            "name": "Content Hook",
            "passed": False,
            "reason": reason,
        },
    }


def block_execution(blocking_message: str, reason: str) -> dict[str, Any]:
    """
    Stop the pipeline and return a message directly to the user.

    The returned event has ``event_type = "response"``.  This is the signal
    Domyn uses to treat the event as a final answer rather than a modified
    input — no further agents, tools, or LLM calls will be made for this
    turn. The original event that triggered the hook is discarded for safety.

    ``passed`` is ``False`` because the request was rejected.
    """
    blocking_event: dict[str, Any] = {
        "event_type": "response",  # ← must be "response" to interrupt
        "author": "content_hook",
        "timestamp": datetime.now().isoformat(),
        "event_id": f"event_{uuid.uuid4()}",
        "content": [{"text": blocking_message}],
        "is_partial": False,
        "need_feedback": False,
        "metadata": {},
    }

    return {
        "modified_event": blocking_event,
        "emitted_content": {
            "name": "Content Hook",
            "passed": False,
            "reason": reason,
        },
    }


def return_error(error_code: str, error_message: str) -> dict[str, Any]:
    """
    Signal a processing failure to the runner.

    Use this when your hook cannot evaluate the event (e.g. an external
    service is unavailable).  The runner will handle the error and break the execution; it will NOT use a ``modified_event``
    from this response.
    """
    return {
        "error_code": error_code,
        "error_message": error_message,
    }


# ---------------------------------------------------------------------------
# Minimal business logic — intentionally trivial
#
# Replace everything below this line with your own policy.
# The three outcomes (pass / modify / block) are what matter structurally.
# ---------------------------------------------------------------------------

# Matches a basic email address anywhere in the text.
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Phrase that triggers an outright block (stand-in for a real policy rule).
_BLOCKED_PHRASE = "ignore all previous instructions"


def _extract_text(event: dict[str, Any]) -> str:
    """Concatenate all text parts from an event's content list."""
    return " ".join(part.get("text", "") for part in event.get("content", []))


def _check_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Apply the hook policy to a single event and return the appropriate result.

    Decision tree
    -------------
    1. Blocked phrase detected  → block_execution (interrupts the pipeline)
    2. Email address detected   → modify_event    (redacts and continues)
    3. No issues                → pass_through    (continues unchanged)

    This is the ONLY function you need to replace when adapting this
    blueprint for a real policy.
    """
    text = _extract_text(event)

    # ── Pattern 3: Block ────────────────────────────────────────────────────
    # The phrase signals a prompt-injection attempt; stop execution entirely.
    if _BLOCKED_PHRASE in text.lower():
        return block_execution(
            blocking_message="I'm sorry, I cannot process that request.",
            reason=f"Blocked phrase detected: '{_BLOCKED_PHRASE}'.",
        )

    # ── Pattern 2: Modify ───────────────────────────────────────────────────
    # An email address is PII; redact it and let the pipeline continue with
    # the sanitised text.
    if _EMAIL_PATTERN.search(text):
        redacted = _EMAIL_PATTERN.sub("[REDACTED EMAIL]", text)
        return modify_event(
            event=event,
            new_text=redacted,
            reason="Email address redacted from content.",
        )

    # ── Pattern 1: Pass-through ─────────────────────────────────────────────
    # Nothing suspicious; forward the event unchanged.
    return pass_through(event)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Content Hook — Minimal Example",
    description=(
        "Demonstrates the three response patterns for a Domyn REST hook: "
        "pass-through, modify, and block."
    ),
    version="0.1.0",
)


# ── Input guardrail ──────────────────────────────────────────────────────────
# Attach this endpoint to a guardrail configured to run *before the answer*
# in the Domyn platform.  Receives ``user_input`` events (user messages) and
# ``agent_start`` events (agent handoffs, i.e. when an agent calls a sub-agent).


@app.post(
    "/input-guardrail",
    summary="Evaluate a user input or agent-start event",
    response_description=(
        "One of: hook result (modified_event + emitted_content), "
        "or error (error_code + error_message)."
    ),
)
async def run_input_guardrail(body: HookRequest) -> dict[str, Any]:
    return _check_event(body.current_event)


# ── Output guardrail ─────────────────────────────────────────────────────────
# Attach this endpoint to a guardrail configured to run *after the response*
# in the Domyn platform.  Receives ``response`` events.


@app.post(
    "/output-guardrail",
    summary="Evaluate an agent response event",
    response_description=(
        "One of: hook result (modified_event + emitted_content), "
        "or error (error_code + error_message)."
    ),
)
async def run_output_guardrail(body: HookRequest) -> dict[str, Any]:
    return _check_event(body.current_event)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")

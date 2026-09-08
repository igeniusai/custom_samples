"""
Content-safety checks.

Checks run only against "user_input" and "response" events, inspecting the
"text" field of each content block. All other event types/fields are ignored.
"""

import asyncio
import re

from app.config import CheckConfig

CHECK_DELAY_SECONDS = 10

CHECK_LABELS = {
    "pii": "PII",
    "toxicity": "Toxicity",
    "prompt_injection": "Prompt Injection",
}

_CHECKED_EVENT_TYPES = {"user_input", "response"}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TOXIC_RE = re.compile(r"\bstupid\b", re.IGNORECASE)
_PROMPT_INJECTION_PHRASE = "ignore system instructions"


def _extract_text(event: dict) -> str:
    if event.get("event_type") not in _CHECKED_EVENT_TYPES:
        return ""
    content = event.get("content") or []
    return " ".join(block["text"] for block in content if block.get("text"))


async def _check_pii(text: str) -> str:
    await asyncio.sleep(CHECK_DELAY_SECONDS)
    return "failed" if _EMAIL_RE.search(text) else "passed"


async def _check_toxicity(text: str) -> str:
    await asyncio.sleep(CHECK_DELAY_SECONDS)
    return "failed" if _TOXIC_RE.search(text) else "passed"


async def _check_prompt_injection(text: str) -> str:
    await asyncio.sleep(CHECK_DELAY_SECONDS)
    return "failed" if _PROMPT_INJECTION_PHRASE in text.lower() else "passed"


async def run_checks(event: dict, config: CheckConfig) -> dict[str, str]:
    """Run every enabled check against the event's text and return {check_name: status}.

    Each check sleeps for CHECK_DELAY_SECONDS to emulate a heavier operation
    (e.g. a call out to a scanning service); enabled checks run concurrently
    so the total wait is CHECK_DELAY_SECONDS regardless of how many run.
    """
    text = _extract_text(event)
    if not text:
        return {}

    names: list[str] = []
    coros = []
    if config.pii:
        names.append("pii")
        coros.append(_check_pii(text))
    if config.toxicity:
        names.append("toxicity")
        coros.append(_check_toxicity(text))
    if config.prompt_injection:
        names.append("prompt_injection")
        coros.append(_check_prompt_injection(text))

    statuses = await asyncio.gather(*coros)
    return dict(zip(names, statuses))

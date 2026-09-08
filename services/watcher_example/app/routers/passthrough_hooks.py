"""
Pass-through before/after hooks.

Not part of the watcher blueprint itself: these exist so a canvas can carry a watcher
hook AND ordinary input/output hooks at the same time without pulling in a second
service. They observe and acknowledge, never modify or block — so the conversation
behaves exactly as it would with no hook at all, while still exercising the real
before/after hook execution path.

Each call is recorded in memory so a caller can assert that a hook really ran on a given
turn. That is deliberately kept SEPARATE from the watcher's event history: a scenario
asserting on recorded agent events must not be polluted by these invocations, and
"was the input hook invoked?" must be answerable independently of whether the watcher
received the corresponding `hook_start`/`hook_end` events.
"""

import logging
from datetime import datetime

from fastapi import APIRouter

from app.config import hook_state
from app.models import HookRequest, HookResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["passthrough-hooks"])

INPUT_HOOK = "input"
OUTPUT_HOOK = "output"


def _record(hook: str, request: HookRequest) -> HookResult:
    event = request.current_event or {}
    turn_id = event.get("turn_id")
    hook_state.invocations.setdefault(hook, []).append(
        {
            "received_at": datetime.now().isoformat(),
            "turn_id": str(turn_id) if turn_id is not None else None,
            "event_type": event.get("event_type"),
            "author": event.get("author"),
        }
    )
    logger.info(
        "%s_hook: acknowledged event_type=%s turn_id=%s",
        hook,
        event.get("event_type"),
        turn_id,
    )
    return HookResult()


@router.post("/input_hook")
async def input_hook(request: HookRequest) -> HookResult:
    """Acknowledges a user request unchanged (timing "before the answer")."""
    return _record(INPUT_HOOK, request)


@router.post("/output_hook")
async def output_hook(request: HookRequest) -> HookResult:
    """Acknowledges an agent answer unchanged (timing "after the answer")."""
    return _record(OUTPUT_HOOK, request)


@router.get("/hooks/invocations")
async def get_hook_invocations(turn_id: str | None = None) -> dict[str, list[dict]]:
    """Recorded pass-through hook calls, optionally narrowed to one turn."""
    if turn_id is None:
        return dict(hook_state.invocations)
    return {
        hook: [call for call in calls if call["turn_id"] == turn_id]
        for hook, calls in hook_state.invocations.items()
    }


@router.delete("/hooks/invocations")
async def clear_hook_invocations() -> dict[str, int]:
    """Drops the recorded calls, so a test run starts from a known-empty state."""
    dropped = sum(len(calls) for calls in hook_state.invocations.values())
    hook_state.invocations.clear()
    logger.info("clear_hook_invocations: dropped %s call(s)", dropped)
    return {"dropped": dropped}

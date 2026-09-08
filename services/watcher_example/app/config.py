"""
Shared in-memory state for the watcher app.

Received events are kept in memory only (cleared on restart) and are never
persisted to disk — this is a lightweight observability example, not a
production audit log.
"""

from pathlib import Path

from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"


class EventState(BaseModel):
    history: dict[str, list[dict]] = Field(default_factory=dict)


event_state = EventState()


class CheckConfig(BaseModel):
    pii: bool = False
    toxicity: bool = False
    prompt_injection: bool = False


check_config = CheckConfig()


class HookState(BaseModel):
    """Calls received by the pass-through before/after hooks, keyed by hook name.

    Separate from EventState so that asserting on the watcher's recorded events and
    asserting on "was the input hook invoked?" stay independent of each other.
    """

    invocations: dict[str, list[dict]] = Field(default_factory=dict)


hook_state = HookState()

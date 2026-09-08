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


MAX_HISTORY_TURNS = 200
"""How many turns the history keeps before dropping the oldest.

The store is shared by every caller, so the alternative — letting a client wipe it to
keep it small — means wiping turns that someone else is still collecting. Bounding it
here keeps that concern out of the callers entirely. 200 turns is far more than any run
needs and small enough to stay in memory.
"""


class EventState(BaseModel):
    history: dict[str, list[dict]] = Field(default_factory=dict)

    def record(self, turn_id: str, entry: dict) -> None:
        """Appends an event to its turn, evicting the oldest turns past the cap.

        Insertion-ordered, so the first keys are the oldest turns. A turn already in the
        history is not re-ordered by a new event: it keeps its original position and is
        evicted on its own age, which is what makes eviction predictable while a long
        turn is still receiving events.
        """
        self.history.setdefault(turn_id, []).append(entry)
        while len(self.history) > MAX_HISTORY_TURNS:
            self.history.pop(next(iter(self.history)))


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

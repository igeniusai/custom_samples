import logging
import string
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import HTMLResponse

from app.checks import run_checks
from app.config import TEMPLATES_DIR, CheckConfig, check_config, event_state
from app.models import HookRequest, HookResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["watcher"])


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------


def _render_history_ui() -> str:
    tpl = string.Template((TEMPLATES_DIR / "event_history_ui.html").read_text())
    return tpl.substitute(
        title="Watcher Example",
        data_path="/watch_event/event-history/data",
    )


def _render_settings_ui() -> str:
    tpl = string.Template((TEMPLATES_DIR / "settings_ui.html").read_text())
    return tpl.substitute(
        title="Watcher Example",
        post_path="/watch_event/settings",
        pii_checked="checked" if check_config.pii else "",
        toxicity_checked="checked" if check_config.toxicity else "",
        prompt_injection_checked="checked" if check_config.prompt_injection else "",
    )


def _get_event_data(message_id: str | None) -> dict[str, list[dict]]:
    if message_id is not None:
        return {message_id: event_state.history.get(message_id, [])}
    return dict(event_state.history)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


async def _run_checks_in_background(entry: dict, config: CheckConfig) -> None:
    entry["checks"] = await run_checks(entry["event"], config)


@router.post("/watch_event")
async def watch_event(request: HookRequest, background_tasks: BackgroundTasks) -> HookResult:
    logger.info("watch_event: %s", request.model_dump())

    event = request.current_event or {}
    turn_id = event.get("turn_id")
    if turn_id is not None:
        entry = {"received_at": datetime.now().isoformat(), "event": event, "checks": {}}
        event_state.history.setdefault(str(turn_id), []).append(entry)
        background_tasks.add_task(_run_checks_in_background, entry, check_config)
    else:
        logger.info("watch_event: event NOT recorded in history — turn_id is None")

    return HookResult()


@router.get("/watch_event/event-history/data")
async def get_event_history_data(message_id: str | None = None) -> dict:
    return _get_event_data(message_id)


@router.delete("/watch_event/event-history/data")
async def clear_event_history(message_id: str | None = None) -> dict[str, int]:
    """Drop recorded events, so a test run starts from a known-empty history.

    Without `message_id` the whole history is cleared; with it, only that turn.
    Returns how many turns were dropped (0 when there was nothing to drop, so
    the call stays idempotent).
    """
    if message_id is not None:
        dropped = 1 if event_state.history.pop(message_id, None) is not None else 0
    else:
        dropped = len(event_state.history)
        event_state.history.clear()

    logger.info("clear_event_history: dropped %s turn(s)", dropped)
    return {"dropped": dropped}


@router.get("/watch_event/event-history", response_class=HTMLResponse)
async def get_event_history_ui() -> HTMLResponse:
    return HTMLResponse(content=_render_history_ui())


@router.post("/watch_event/settings")
async def update_check_settings(body: CheckConfig) -> dict[str, str]:
    check_config.pii = body.pii
    check_config.toxicity = body.toxicity
    check_config.prompt_injection = body.prompt_injection
    return {"status": "ok"}


@router.get("/watch_event/settings/data")
async def get_check_settings_data() -> CheckConfig:
    """The current check configuration as JSON.

    Lets a caller assert what was saved without scraping the settings iframe.
    """
    return check_config


@router.get("/watch_event/settings", response_class=HTMLResponse)
async def get_check_settings_ui() -> HTMLResponse:
    return HTMLResponse(content=_render_settings_ui())


@router.get("/watch_event/.well-known/domyn-custom-ui")
async def get_custom_ui_metadata() -> dict[str, Any]:
    return {
        "name": "watcher-example",
        "version": "0.1.0",
        "views": [
            {
                "id": "watcher-event-history",
                "label": {
                    "default": "Received Events",
                    "it": "Eventi ricevuti",
                },
                "description": {
                    "default": "View the raw events the watcher received for this message.",
                    "it": "Visualizza gli eventi grezzi ricevuti dal watcher per questo messaggio.",
                },
                "path": "/watch_event/event-history",
                "locations": ["message"],
                "icon": None,
            },
            {
                "id": "watcher-check-settings",
                "label": {
                    "default": "Check Settings",
                    "it": "Impostazioni controlli",
                },
                "description": {
                    "default": "Choose which checks (PII, Toxicity, Prompt Injection) run against received events.",
                    "it": "Scegli quali controlli (PII, Tossicità, Prompt Injection) eseguire sugli eventi ricevuti.",
                },
                "path": "/watch_event/settings",
                "locations": ["space"],
                "icon": None,
            },
        ],
    }

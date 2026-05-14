"""
Input guardrail router.

POST /input-guardrail                            — evaluate a user_input / agent_start event
POST /input-guardrail/judge-settings             — update LLM config + policy
GET  /input-guardrail/judge-settings             — admin UI
GET  /input-guardrail/verdict-history            — verdict history UI
GET  /input-guardrail/verdict-history/data       — verdict history JSON
GET  /input-guardrail/.well-known/domyn-custom-ui — discovery metadata
"""

import string
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.config import TEMPLATES_DIR, GuardrailState, JudgeVerdict, input_state, save_state
from app.judge import evaluate
from app.models import GuardrailRequest

router = APIRouter(prefix="/input-guardrail", tags=["input-guardrail"])

_GUARDRAIL_NAME = "input_guardrail"


# ---------------------------------------------------------------------------
# Template helpers (local to this router)
# ---------------------------------------------------------------------------


def _render_admin_ui(state: GuardrailState) -> str:
    api_key_hint = (
        '<div class="field-hint has-key">An API key is currently set. Leave blank to keep it.</div>'
        if state.api_key
        else ""
    )
    tpl = string.Template((TEMPLATES_DIR / "admin_ui.html").read_text())
    return tpl.substitute(
        title="Input Guardrail",
        subtitle="Policy applied to user inputs and agent-start events.",
        post_path="/input-guardrail/judge-settings",
        model_val=state.model_name or "",
        url_val=state.url or "",
        api_key_hint=api_key_hint,
        policy_val=state.policy or "",
    )


def _render_history_ui() -> str:
    tpl = string.Template((TEMPLATES_DIR / "verdict_history_ui.html").read_text())
    return tpl.substitute(
        title="Input Guardrail",
        data_path="/input-guardrail/verdict-history/data",
    )


def _get_verdict_data(message_id: str | None) -> dict[str, list[dict]]:
    def serialise(verdicts: list[JudgeVerdict]) -> list[dict]:
        return [v.model_dump() for v in verdicts]

    if message_id is not None:
        return {message_id: serialise(input_state.verdict_history.get(message_id, []))}
    return {tid: serialise(vs) for tid, vs in input_state.verdict_history.items()}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("")
async def run_input_guardrail(body: GuardrailRequest) -> dict[str, Any]:
    return await evaluate(body, input_state, _GUARDRAIL_NAME)


@router.post("/judge-settings")
async def update_input_configuration(body: GuardrailState) -> dict[str, str]:
    if body.policy is not None:
        input_state.policy = body.policy
    if body.model_name:
        input_state.model_name = body.model_name
    if body.url:
        input_state.url = body.url
    if body.api_key:
        input_state.api_key = body.api_key
    save_state(input_state, "input_guardrail")
    return {"status": "ok"}


@router.get("/judge-settings", response_class=HTMLResponse)
async def get_input_admin_ui() -> HTMLResponse:
    return HTMLResponse(content=_render_admin_ui(input_state))


@router.get("/verdict-history/data")
async def get_input_verdict_history_data(message_id: str | None = None) -> dict:
    return _get_verdict_data(message_id)


@router.get("/verdict-history", response_class=HTMLResponse)
async def get_input_verdict_history_ui() -> HTMLResponse:
    return HTMLResponse(content=_render_history_ui())


@router.get("/.well-known/domyn-custom-ui")
async def get_input_custom_ui_metadata() -> dict[str, Any]:
    return {
        "name": "input-judge-guardrail",
        "version": "0.1.0",
        "views": [
            {
                "id": "input-guardrail-admin",
                "label": {
                    "default": "Input Guardrail",
                    "it": "Guardrail input",
                    "de": "Eingabe-Guardrail",
                    "fr": "Garde-fou entrée",
                    "es": "Guardrail de entrada",
                },
                "description": {
                    "default": "Configure the policy applied to user inputs and agent-start events.",
                    "it": "Configura la policy applicata agli input utente e agli eventi agent_start.",
                },
                "path": "/input-guardrail/judge-settings",
                "locations": ["space"],
                "icon": None,
            },
            {
                "id": "input-guardrail-history",
                "label": {
                    "default": "Input Verdict History",
                    "it": "Storico verdetti input",
                    "de": "Eingabe-Verlauf",
                    "fr": "Historique entrée",
                    "es": "Historial de entrada",
                },
                "description": {
                    "default": "View the verdict history for user inputs and agent-start events.",
                    "it": "Visualizza lo storico dei verdetti per gli input utente e gli eventi agent_start.",
                },
                "path": "/input-guardrail/verdict-history",
                "locations": ["message"],
                "icon": None,
            },
        ],
    }

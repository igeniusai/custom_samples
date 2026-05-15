"""
Output guardrail router.

POST /output-guardrail                            — evaluate a response event
POST /output-guardrail/judge-settings             — update LLM config + policy
GET  /output-guardrail/judge-settings             — admin UI
GET  /output-guardrail/verdict-history            — verdict history UI
GET  /output-guardrail/verdict-history/data       — verdict history JSON
GET  /output-guardrail/.well-known/domyn-custom-ui — discovery metadata
"""

import string
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.config import TEMPLATES_DIR, GuardrailState, JudgeVerdict, output_state, save_state
from app.judge import evaluate
from app.models import GuardrailRequest

router = APIRouter(prefix="/output-guardrail", tags=["output-guardrail"])

_GUARDRAIL_NAME = "output_guardrail"


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
        title="Output Guardrail",
        subtitle="Policy applied to agent response events.",
        post_path="/output-guardrail/judge-settings",
        model_val=state.model_name or "",
        url_val=state.url or "",
        api_key_hint=api_key_hint,
        policy_val=state.policy or "",
    )


def _render_history_ui() -> str:
    tpl = string.Template((TEMPLATES_DIR / "verdict_history_ui.html").read_text())
    return tpl.substitute(
        title="Output Guardrail",
        data_path="/output-guardrail/verdict-history/data",
    )


def _get_verdict_data(message_id: str | None) -> dict[str, list[dict]]:
    def serialise(verdicts: list[JudgeVerdict]) -> list[dict]:
        return [v.model_dump() for v in verdicts]

    if message_id is not None:
        return {message_id: serialise(output_state.verdict_history.get(message_id, []))}
    return {tid: serialise(vs) for tid, vs in output_state.verdict_history.items()}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("")
async def run_output_guardrail(body: GuardrailRequest) -> dict[str, Any]:
    return await evaluate(body, output_state, _GUARDRAIL_NAME)


@router.post("/judge-settings")
async def update_output_configuration(body: GuardrailState) -> dict[str, str]:
    if body.policy is not None:
        output_state.policy = body.policy
    if body.model_name:
        output_state.model_name = body.model_name
    if body.url:
        output_state.url = body.url
    if body.api_key:
        output_state.api_key = body.api_key
    save_state(output_state, "output_guardrail")
    return {"status": "ok"}


@router.get("/judge-settings", response_class=HTMLResponse)
async def get_output_admin_ui() -> HTMLResponse:
    return HTMLResponse(content=_render_admin_ui(output_state))


@router.get("/verdict-history/data")
async def get_output_verdict_history_data(message_id: str | None = None) -> dict:
    return _get_verdict_data(message_id)


@router.get("/verdict-history", response_class=HTMLResponse)
async def get_output_verdict_history_ui() -> HTMLResponse:
    return HTMLResponse(content=_render_history_ui())


@router.get("/.well-known/domyn-custom-ui")
async def get_output_custom_ui_metadata() -> dict[str, Any]:
    return {
        "name": "output-judge-guardrail",
        "version": "0.1.0",
        "views": [
            {
                "id": "output-guardrail-admin",
                "label": {
                    "default": "Output Guardrail",
                    "it": "Guardrail output",
                    "de": "Ausgabe-Guardrail",
                    "fr": "Garde-fou sortie",
                    "es": "Guardrail de salida",
                },
                "description": {
                    "default": "Configure the policy applied to agent response events.",
                    "it": "Configura la policy applicata alle risposte dell'agente.",
                },
                "path": "/output-guardrail/judge-settings",
                "locations": ["space"],
                "icon": None,
            },
            {
                "id": "output-guardrail-history",
                "label": {
                    "default": "Output Verdict History",
                    "it": "Storico verdetti output",
                    "de": "Ausgabe-Verlauf",
                    "fr": "Historique sortie",
                    "es": "Historial de salida",
                },
                "description": {
                    "default": "View the verdict history for agent response events.",
                    "it": "Visualizza lo storico dei verdetti per le risposte dell'agente.",
                },
                "path": "/output-guardrail/verdict-history",
                "locations": ["message"],
                "icon": None,
            },
        ],
    }

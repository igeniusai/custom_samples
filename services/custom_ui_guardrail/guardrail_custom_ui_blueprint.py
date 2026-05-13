"""
Blueprint: Dual Judge Guardrail Service
========================================
Two independent guardrail hooks, each with its own policy, LLM config,
REST endpoint, and admin UI:

  • Input guardrail  — fires on ``user_input`` and ``agent_start`` events.
  • Output guardrail — fires on ``response`` events.

Both are registered as ``on_agent_event`` REST hooks in the Domyn YAML
config. Each hook passes through any event it does not own unchanged, so
they can coexist on the same agent without interfering.

Endpoints
---------
POST /input-guardrail
    Evaluate a user_input / agent_start event.

GET  /input-guardrail/judge-settings
    Admin iFrame page for the input guardrail (values pre-filled from current state).

POST /input-guardrail/judge-settings
    Update the input guardrail policy and LLM provider.

POST /output-guardrail
    Evaluate a response event.

GET  /output-guardrail/judge-settings
    Admin iFrame page for the output guardrail (values pre-filled from current state).

POST /output-guardrail/judge-settings
    Update the output guardrail policy and LLM provider.

GET  /input-guardrail/.well-known/domyn-custom-ui
    Discovery endpoint — returns JSON metadata for the input guardrail admin view only.

GET  /output-guardrail/.well-known/domyn-custom-ui
    Discovery endpoint — returns JSON metadata for the output guardrail admin view only.

Run
---
    pip install fastapi uvicorn httpx pydantic
    uvicorn blueprint:app --reload --port 9001
"""

import asyncio
import copy
import json
import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# Per-guardrail in-memory state
# ---------------------------------------------------------------------------

DEFAULT_POLICY = """
1. Mask all PIIs with the string "[PII:<input pii type>]", e.g. "My email is [PII:email]". Mask the following PII types:
\t- Name/Surname
\t- Email
\t- Phone number
\t- Address
\t- Credit card number
\t- Social security number
\t- Date of birth
\t- Salary
\t- IBAN
2. Block any content that contains profanity, hate speech, or adult content.
3. Block any content containing or requesting medical advice.
4. Block any content that doesn't comply with all applicable laws and regulations, including data protection and privacy laws.
"""


class GuardrailState(BaseSettings):
    policy: str | None = DEFAULT_POLICY
    model_name: str | None = None
    url: str | None = None
    api_key: str | None = None


_input_state = GuardrailState()
_output_state = GuardrailState()


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a content-safety judge for an agentic system. \
Evaluate whether the provided text complies with the policy below, \
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

_MAX_RETRIES = 3


class Verdict(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class JudgeVerdict(BaseModel):
    verdict: Verdict
    reason: str
    output: str


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
        return response.json()["choices"][0]["message"]["content"]


def _extract_json(text: str) -> str:
    """Strip markdown fences and return the first JSON object found in text."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ``` fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        return fenced.group(1).strip()
    # Fall back to the first {...} block
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        return brace.group(0)
    return text


_RETRY_PROMPT = (
    "Your previous response could not be parsed. "
    "Return ONLY a raw JSON object — no markdown, no extra text. "
    "Required fields: "
    '"verdict" (exactly one of "approved", "rejected", "modified"), '
    '"reason" (string), '
    '"output" (string). '
    'Example: {{"verdict": "approved", "reason": "Complies with policy.", "output": ""}}'
)


async def _generate_verdict(messages: list[dict[str, str]], state: GuardrailState) -> JudgeVerdict:
    history = list(messages)
    last_error: Exception | None = None
    content: str = ""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            content = await _call_llm(history, state)
            return JudgeVerdict.model_validate_json(_extract_json(content))
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code
            snippet = exc.response.text[:200]
            print(
                f"[guardrail] attempt {attempt}/{_MAX_RETRIES} LLM returned HTTP {status}: {snippet}"
            )
            if status < 500:
                # 4xx errors won't recover with a retry
                raise
            await asyncio.sleep(1.0 * attempt)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            print(
                f"[guardrail] attempt {attempt}/{_MAX_RETRIES} malformed output: {exc}\nRaw: {content!r}"
            )
            history = [
                *history,
                {"role": "assistant", "content": content},
                {"role": "user", "content": _RETRY_PROMPT},
            ]
    raise RuntimeError(f"Guardrail failed after {_MAX_RETRIES} attempts") from last_error


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class GuardrailRequest(BaseModel):
    current_event: dict
    interaction_history: list[dict] = []


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_event(event_type: str, author: str, text: str) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "author": author,
        "timestamp": datetime.now().isoformat(),
        "event_id": f"event_{uuid.uuid4()}",
        "content": [{"text": text}],
        "is_partial": False,
        "need_feedback": False,
        "metadata": {},
    }


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


async def _evaluate(
    body: GuardrailRequest,
    state: GuardrailState,
    guardrail_name: str,
) -> dict[str, Any]:
    event = body.current_event

    if not state.model_name or not state.url:
        reason = f"LLM provider not configured for {guardrail_name}. Use the admin UI to set model_name, url, and optionally api_key."
        print(f"[guardrail] {guardrail_name}: {reason}")
        return _make_hook_result(copy.deepcopy(event), True, reason, guardrail_name)

    event_type = event.get("event_type", "event")
    content_text = "\n".join((part.get("text") or "") for part in event.get("content", []))

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT.format(policy=state.policy)},
        {
            "role": "user",
            "content": f"Judge the following {event_type} according to the policy.\n\n{content_text}",
        },
    ]

    try:
        verdict = await _generate_verdict(messages, state)
    except httpx.HTTPStatusError as exc:
        error = f"LLM provider returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        print(f"[guardrail] {guardrail_name} error: {error}")
        return _make_hook_result(copy.deepcopy(event), True, error, guardrail_name)
    except Exception as exc:
        error = str(exc)
        print(f"[guardrail] {guardrail_name} error: {error}")
        return _make_hook_result(copy.deepcopy(event), True, error, guardrail_name)

    output_event = copy.deepcopy(event)

    match verdict.verdict:
        case Verdict.APPROVED:
            passed = True
        case Verdict.REJECTED:
            output_event["event_type"] = "response"
            output_event["author"] = guardrail_name
            output_event["content"] = [
                {"text": verdict.output or "Your message was blocked by the system."}
            ]
            output_event["timestamp"] = datetime.now().isoformat()
            output_event["event_id"] = str(uuid.uuid4())
            output_event["is_partial"] = False
            passed = False
        case Verdict.MODIFIED:
            output_event["content"] = [{"text": verdict.output}]
            if output_event["event_type"] == "agent_start":
                output_event["action"]["parameters"] = {"task": verdict.output}

            passed = False
        case _:
            passed = True

    return _make_hook_result(output_event, passed, verdict.reason, guardrail_name)


async def _update_config(body: GuardrailState, state: GuardrailState) -> dict:
    state.policy = body.policy
    if body.model_name:
        state.model_name = body.model_name
    if body.url:
        state.url = body.url
    if body.api_key:
        state.api_key = body.api_key
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Dual Judge Guardrail", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Input guardrail ─────────────────────────────────────────────────────────


@app.post("/input-guardrail")
async def run_input_guardrail(body: GuardrailRequest) -> dict:
    return await _evaluate(body, _input_state, "input_guardrail")


@app.post("/input-guardrail/judge-settings")
async def update_input_configuration(body: GuardrailState) -> dict:
    return await _update_config(body, _input_state)


@app.get("/input-guardrail/judge-settings", response_class=HTMLResponse)
async def get_input_admin_ui() -> HTMLResponse:
    return HTMLResponse(
        content=_render_admin_ui(
            title="Input Guardrail",
            subtitle="Policy applied to user inputs and agent-start events.",
            post_path="/input-guardrail/judge-settings",
            state=_input_state,
        )
    )


# ── Output guardrail ────────────────────────────────────────────────────────


@app.post("/output-guardrail")
async def run_output_guardrail(body: GuardrailRequest) -> dict:
    return await _evaluate(body, _output_state, "output_guardrail")


@app.post("/output-guardrail/judge-settings")
async def update_output_configuration(body: GuardrailState) -> dict:
    return await _update_config(body, _output_state)


@app.get("/output-guardrail/judge-settings", response_class=HTMLResponse)
async def get_output_admin_ui() -> HTMLResponse:
    return HTMLResponse(
        content=_render_admin_ui(
            title="Output Guardrail",
            subtitle="Policy applied to agent response events.",
            post_path="/output-guardrail/judge-settings",
            state=_output_state,
        )
    )


# ── Discovery ───────────────────────────────────────────────────────────────


@app.get("/input-guardrail/.well-known/domyn-custom-ui")
async def get_input_custom_ui_metadata() -> dict:
    """Discovery endpoint — returns JSON metadata for the input guardrail admin view."""
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
        ],
    }


@app.get("/output-guardrail/.well-known/domyn-custom-ui")
async def get_output_custom_ui_metadata() -> dict:
    """Discovery endpoint — returns JSON metadata for the output guardrail admin view."""
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
        ],
    }


# ---------------------------------------------------------------------------
# Shared admin UI template
# ---------------------------------------------------------------------------


def _render_admin_ui(title: str, subtitle: str, post_path: str, state: GuardrailState) -> str:
    policy_val = state.policy or ""
    model_val = state.model_name or ""
    url_val = state.url or ""
    api_key_hint = (
        '<div class="field-hint has-key">An API key is currently set. Leave blank to keep it.</div>'
        if state.api_key
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Configuration</title>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f0f2f5;
            color: #1a2332;
            margin: 0;
            padding: 32px 16px 64px;
            font-size: 14px;
            line-height: 1.5;
        }}

        body.dark {{
            background: #0d1117;
            color: #e6edf3;
        }}

        .page-header {{
            max-width: 680px;
            margin: 0 auto 28px;
            padding-bottom: 20px;
            border-bottom: 1px solid #d5dbe4;
        }}

        body.dark .page-header {{ border-bottom-color: #30363d; }}

        .page-header h1 {{
            font-size: 20px;
            font-weight: 600;
            color: #0d1b2e;
            margin: 0 0 4px;
            letter-spacing: -0.2px;
        }}

        body.dark .page-header h1 {{ color: #e6edf3; }}

        .page-header p {{
            color: #5a6a7e;
            margin: 0;
            font-size: 13px;
        }}

        .card {{
            background: #ffffff;
            border: 1px solid #d5dbe4;
            border-radius: 6px;
            max-width: 680px;
            margin: 0 auto 20px;
            overflow: hidden;
        }}

        body.dark .card {{ background: #161b22; border-color: #30363d; }}

        .card-header {{
            padding: 14px 20px;
            border-bottom: 1px solid #e8ecf0;
            background: #f8f9fb;
        }}

        body.dark .card-header {{ background: #1c2129; border-bottom-color: #30363d; }}

        .card-header h2 {{
            font-size: 13px;
            font-weight: 600;
            color: #1a2332;
            margin: 0;
            text-transform: uppercase;
            letter-spacing: 0.6px;
        }}

        body.dark .card-header h2 {{ color: #e6edf3; }}

        .card-body {{ padding: 20px; }}

        .field {{ margin-bottom: 16px; }}
        .field:last-child {{ margin-bottom: 0; }}

        label {{
            display: block;
            font-size: 12px;
            font-weight: 600;
            color: #3d4f63;
            margin-bottom: 5px;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }}

        body.dark label {{ color: #8b949e; }}

        input[type="text"],
        input[type="password"],
        textarea {{
            width: 100%;
            padding: 9px 12px;
            border: 1px solid #c8d0da;
            border-radius: 4px;
            font-size: 13px;
            font-family: inherit;
            color: #1a2332;
            background: #ffffff;
            transition: border-color 0.15s, box-shadow 0.15s;
            outline: none;
        }}

        body.dark input[type="text"],
        body.dark input[type="password"],
        body.dark textarea {{
            background: #0d1117;
            border-color: #30363d;
            color: #e6edf3;
        }}

        input[type="text"]:focus,
        input[type="password"]:focus,
        textarea:focus {{
            border-color: #2563a8;
            box-shadow: 0 0 0 3px rgba(37, 99, 168, 0.12);
        }}

        input::placeholder, textarea::placeholder {{ color: #a0aab5; }}
        textarea {{ height: 140px; resize: vertical; line-height: 1.55; }}

        .field-hint {{ font-size: 11.5px; color: #7a8fa6; margin-top: 4px; }}
        .field-hint.has-key {{ color: #2d7a4f; font-weight: 500; }}

        .card-footer {{
            padding: 14px 20px;
            border-top: 1px solid #e8ecf0;
            background: #f8f9fb;
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        body.dark .card-footer {{ background: #1c2129; border-top-color: #30363d; }}

        button {{
            padding: 8px 22px;
            background: #1a3f6f;
            color: #ffffff;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            font-family: inherit;
            letter-spacing: 0.2px;
            transition: background 0.15s;
        }}

        button:hover {{ background: #163460; }}
        button:active {{ background: #112a4f; }}

        #status {{ font-size: 13px; display: none; padding: 4px 0; }}
        .success {{ color: #1a6b3c; }}
        .error   {{ color: #9b1c1c; }}
    </style>
</head>
<body>
    <div class="page-header">
        <h1>{title}</h1>
        <p>{subtitle}</p>
    </div>

    <div class="card">
        <div class="card-header"><h2>LLM Provider</h2></div>
        <div class="card-body">
            <div class="field">
                <label for="model-name">Model name</label>
                <input type="text" id="model-name" placeholder="e.g. Qwen/Qwen3-32B" value="{model_val}">
            </div>
            <div class="field">
                <label for="inference-url">Inference URL</label>
                <input type="text" id="inference-url" placeholder="e.g. http://llm-server/v1/chat/completions" value="{url_val}">
            </div>
            <div class="field">
                <label for="api-key">API key</label>
                <input type="password" id="api-key" placeholder="Leave blank to keep the existing key if already set">
                {api_key_hint}
            </div>
        </div>
    </div>

    <div class="card">
        <div class="card-header"><h2>Guardrail Policy</h2></div>
        <div class="card-body">
            <div class="field">
                <label for="text-input">Instruction</label>
                <textarea id="text-input" placeholder="Enter guardrail instruction...">{policy_val}</textarea>
            </div>
        </div>
        <div class="card-footer">
            <button onclick="saveConfig()">Save configuration</button>
            <div id="status"></div>
        </div>
    </div>

    <script>
        const POST_PATH = '{post_path}';
        const statusEl = document.getElementById('status');

        // Read display hints from URL params; request full auth context via postMessage.
        const urlParams = new URLSearchParams(window.location.search);
        applyTheme(urlParams.get('theme') || 'light');

        let authorizationHeader = null;

        function applyTheme(theme) {{
            document.body.classList.toggle('dark', theme === 'dark');
        }}

        window.parent.postMessage({{ type: 'request-params' }}, '*');

        window.addEventListener('message', function(event) {{
            if (!event.data || event.data.type !== 'params') return;
            if (event.data.theme) applyTheme(event.data.theme);
            if (event.data.authorization) authorizationHeader = event.data.authorization;
        }});

        function buildHeaders() {{
            const headers = {{ 'Content-Type': 'application/json' }};
            if (authorizationHeader) headers['Authorization'] = authorizationHeader;
            return headers;
        }}

        function showStatus(message, success) {{
            statusEl.textContent = message;
            statusEl.className = success ? 'success' : 'error';
            statusEl.style.display = 'block';
        }}

        async function saveConfig() {{
            const policy = document.getElementById('text-input').value.trim();
            const model_name = document.getElementById('model-name').value.trim();
            const url = document.getElementById('inference-url').value.trim();
            const api_key = document.getElementById('api-key').value;

            if (!policy) {{ showStatus('Please enter a guardrail instruction before saving.', false); return; }}
            if (!model_name || !url) {{ showStatus('Please fill in both model name and inference URL.', false); return; }}

            const body = {{ policy, model_name, url }};
            if (api_key) body.api_key = api_key;

            try {{
                const resp = await fetch(POST_PATH, {{
                    method: 'POST',
                    headers: buildHeaders(),
                    body: JSON.stringify(body),
                }});
                const data = await resp.json();
                if (resp.ok) {{
                    showStatus('Configuration saved successfully.', true);
                    document.getElementById('api-key').value = '';
                }} else {{
                    showStatus(data.detail || 'Error saving configuration.', false);
                }}
            }} catch (e) {{
                showStatus('Network error: ' + e.message, false);
            }}
        }}

    </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")

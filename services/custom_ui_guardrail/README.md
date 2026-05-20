# Domyn Platform — Dual Judge Guardrail Blueprint

A ready-to-run guardrail service for the Domyn platform. Exposes two independent LLM-based guardrail hooks — one for user inputs, one for agent responses — each with its own configurable policy and admin UI embedded directly in the platform canvas.

---

## What's included

```
custom_ui_guardrail/
├── guardrail_custom_ui_blueprint.py   # Entrypoint — re-exports the FastAPI app for uvicorn
├── app/
│   ├── main.py                        # FastAPI app factory and router registration
│   ├── config.py                      # State, settings, and persistence helpers
│   ├── judge.py                       # LLM judge logic
│   ├── models.py                      # Request/response models
│   └── routers/
│       ├── input_guardrail.py         # Input guardrail endpoints
│       └── output_guardrail.py        # Output guardrail endpoints
├── templates/
│   ├── admin_ui.html                  # Admin iFrame UI template
│   └── verdict_history_ui.html        # Verdict history iFrame UI template
├── data/                              # Persisted config files (auto-created at runtime)
├── Dockerfile                         # Container image definition
├── docker-compose.yml                 # One-command local Docker run
└── pyproject.toml                     # Python dependencies
```

---

## Prerequisites

- Python 3.12+ (for local/laptop runs)
- Docker (for containerised runs and VM deployment)
- An OpenAI-compatible LLM endpoint (configured at runtime via the admin UI)

---

## Endpoints

| Method | Path | Description                                                               |
|--------|------|---------------------------------------------------------------------------|
| `POST` | `/input-guardrail` | Evaluate a `user_input` / `agent_start` event                             |
| `GET`  | `/input-guardrail/judge-settings` | Admin iFrame page for the input guardrail, shown in canvas                |
| `POST` | `/input-guardrail/judge-settings` | Update input guardrail policy and LLM config                              |
| `GET`  | `/input-guardrail/verdict-history` | Verdict history iFrame page for the input guardrail, shown after messages |
| `GET`  | `/input-guardrail/verdict-history/data` | Verdict history JSON for the input guardrail                              |
| `GET`  | `/input-guardrail/.well-known/domyn-custom-ui` | Discovery metadata for the input guardrail views                          |
| `POST` | `/output-guardrail` | Evaluate a `response` event                                               |
| `GET`  | `/output-guardrail/judge-settings` | Admin iFrame page for the output guardrail, shown in canvas               |
| `POST` | `/output-guardrail/judge-settings` | Update output guardrail policy and LLM config                             |
| `GET`  | `/output-guardrail/verdict-history` | Verdict history iFrame page for the output guardrail, shown after messages                      |
| `GET`  | `/output-guardrail/verdict-history/data` | Verdict history JSON for the output guardrail                             |
| `GET`  | `/output-guardrail/.well-known/domyn-custom-ui` | Discovery metadata for the output guardrail views                         |

---

## Running locally (laptop)

Install dependencies:

```bash
pip install -e .
```

Start the service:

```bash
uvicorn guardrail_custom_ui_blueprint:app --reload --port 8080
```

The admin UIs are available at:
- `http://localhost:8080/input-guardrail/judge-settings`
- `http://localhost:8080/output-guardrail/judge-settings`

The verdict history UIs are available at:
- `http://localhost:8080/input-guardrail/verdict-history`
- `http://localhost:8080/output-guardrail/verdict-history`

---

## Running with Docker (laptop or VM)

Build the image:

```bash
docker build -t custom-ui-guardrail .
```

Run:

```bash
docker run -p 8080:8080 custom-ui-guardrail
```

Or with Docker Compose (one command):

```bash
docker compose up
```

---

## Deploying to a VM

1. Copy the directory to your VM:

```bash
scp -r custom_ui_guardrail/ user@your-vm:/opt/custom-ui-guardrail/
```

2. SSH into the VM and build:

```bash
ssh user@your-vm
cd /opt/custom-ui-guardrail
docker build -t custom-ui-guardrail .
```

3. Run as a systemd service for automatic restart on reboot:

```ini
# /etc/systemd/system/custom-ui-guardrail.service
[Unit]
Description=Domyn Custom UI Guardrail
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker run --rm -p 8080:8080 \
    --name custom-ui-guardrail custom-ui-guardrail
ExecStop=/usr/bin/docker stop custom-ui-guardrail

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now custom-ui-guardrail
sudo journalctl -fu custom-ui-guardrail   # tail logs
```

---

## Configuring the guardrails

Both guardrails start with the default policy pre-loaded. Use the admin UI (embedded in the Domyn canvas or accessible directly) to set:

| Field | Description |
|-------|-------------|
| **Model name** | The model identifier, e.g. `Qwen/Qwen3-32B` |
| **Inference URL** | OpenAI-compatible chat completions endpoint, e.g. `http://llm-server/v1/chat/completions` |
| **API key** | Optional bearer token for the LLM endpoint |
| **Policy** | Free-text instructions the judge follows when evaluating content |

Settings are persisted to disk in the `data/` directory (`data/input_guardrail.json` and `data/output_guardrail.json`) and survive container restarts. Verdict history is runtime-only and is not persisted.

---

## Default policy

The service ships with a default policy that:

1. Masks PII (names, emails, phone numbers, addresses, credit cards, SSNs, dates of birth, salaries, IBANs)
2. Blocks profanity, hate speech, and adult content
3. Blocks medical advice
4. Blocks content violating applicable laws and regulations

Override it at any time via the admin UI or the `POST /*/judge-settings` endpoint.

---

## How the guardrails work

Each guardrail receives a Domyn platform event and passes the content text to an LLM judge. The judge returns one of three verdicts:

| Verdict | Behaviour |
|---------|-----------|
| `approved` | Event is passed through unchanged |
| `modified` | Event content is replaced with the cleaned version |
| `rejected` | Event is replaced with a blocking message shown to the user |

Each guardrail exposes two custom UI views in the Domyn platform canvas:

| View | Location | Purpose |
|------|----------|---------|
| Admin (judge settings) | Space | Configure the LLM endpoint and policy |
| Verdict history | Message | Inspect per-message verdicts and reasons inline |

The result of each guardrail evaluation is displayed directly in the Domyn platform: a green circle indicates the content passed, a red circle indicates it was blocked or modified. The reason provided by the judge is shown alongside the indicator so users and operators can understand why a decision was made.

On LLM failure or misconfiguration, the hook returns a structured error object instead of blocking the event, so the pipeline is not silently broken.

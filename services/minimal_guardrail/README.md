# Domyn Platform — Minimal Guardrail Blueprint

A minimal, heavily documented example of a Domyn REST hook guardrail. Intended as a starting point and reference: the business logic is intentionally trivial (email redaction + blocked-phrase detection) so the hook contract and the three response patterns stand out clearly.

---

## What's included

```
minimal_guardrail/
├── minimal_guardrail_io_example.py   # FastAPI service — replace the policy logic here
├── Dockerfile                         # Container image definition
├── docker-compose.yml                 # One-command local Docker run
└── requirements.txt                   # Python dependencies
```

---

## Prerequisites

- Python 3.12+ (for local/laptop runs)
- Docker (for containerised runs and VM deployment)

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/input-guardrail` | Evaluate a `user_input` or `agent_start` event (fires before the answer) |
| `POST` | `/output-guardrail` | Evaluate a `response` event (fires after the answer) |

Register each URL in the Domyn platform UI as an `on_agent_event` hook on the target agent.

---

## Running locally (laptop)

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the service:

```bash
uvicorn minimal_guardrail_io_example:app --reload --port 8080
```

---

## Running with Docker (laptop or VM)

Build the image:

```bash
docker build -t minimal-guardrail .
```

Run:

```bash
docker run -p 8080:8080 minimal-guardrail
```

Or with Docker Compose (one command):

```bash
docker compose up
```

---

## Deploying to a VM

1. Copy the directory to your VM:

```bash
scp -r minimal_guardrail/ user@your-vm:/opt/minimal-guardrail/
```

2. SSH into the VM and build:

```bash
ssh user@your-vm
cd /opt/minimal-guardrail
docker build -t minimal-guardrail .
```

3. Run as a systemd service for automatic restart on reboot:

```ini
# /etc/systemd/system/minimal-guardrail.service
[Unit]
Description=Domyn Minimal Guardrail
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker run --rm -p 8080:8080 \
    --name minimal-guardrail minimal-guardrail
ExecStop=/usr/bin/docker stop minimal-guardrail

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now minimal-guardrail
sudo journalctl -fu minimal-guardrail   # tail logs
```

---

## Hook contract

Every POST from the Domyn runner carries:

| Field | Type | Description |
|-------|------|-------------|
| `current_event` | object | The event being evaluated (same shape as in the observability view) |
| `interaction_history` | list | Past events for this conversation, oldest first. May be empty. |

Your hook must return one of three response shapes:

### 1. Pass-through — let the event continue unchanged

```json
{
    "modified_event": { "...original event..." },
    "emitted_content": { "name": "My Hook", "passed": true, "reason": "No issues found." }
}
```

### 2. Modify — alter the content and continue

```json
{
    "modified_event": { "...event with changed content list..." },
    "emitted_content": { "name": "My Hook", "passed": false, "reason": "Email address redacted." }
}
```

### 3. Block — stop the pipeline and return a message to the user

```json
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
    "emitted_content": { "name": "My Hook", "passed": false, "reason": "Request blocked." }
}
```

The key distinction from *modify*: setting `event_type` to `"response"` tells Domyn to treat the event as the final answer for this turn — no further agents or LLM calls are made.

### Error — signal a processing failure

```json
{
    "error_code": "short_snake_case_code",
    "error_message": "Human-readable description of what went wrong."
}
```

The guardrail result is displayed in the Domyn platform: a green circle if `passed` is `true`, a red circle if `false`, with the `reason` shown alongside.

---

## Adapting this blueprint

All business logic is in `_check_event` inside `minimal_guardrail_io_example.py`. Replace or extend it with your own policy. The three helper functions — `pass_through`, `modify_event`, `block_execution` — build the correct response shapes and can be reused as-is.

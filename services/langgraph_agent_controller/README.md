# LangGraph Agent Controller

FastAPI service to configure, start, and stop the `langgraph_agent_example` expose process via HTTP endpoints.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/update` | Save agent configuration |
| `POST` | `/start` | Start the `domyn expose` process |
| `POST` | `/stop` | Stop the running process |
| `GET` | `/status` | Get current process status |
| `GET` | `/health` | Health check |

### POST /update

Saves one or more configuration values. All fields are optional — only provided fields are updated.

```json
{
  "domyn_api_key": "domyn_xxx",
  "channel_id": "abc123",
  "space_id": "uuid-here",
  "platform_base_url": "qa.crystal.io",
  "vllm_api_key": "sk-xxx",
  "vllm_base_url": "https://gateway-dev.llm.crystal.ai/v1",
  "vllm_model": "Qwen/Qwen3-32B"
}
```

Configuration is persisted to `data/config.json`.

### POST /start

Launches the following command as a background subprocess using the saved configuration:

```
domyn expose agent_expose:graph \
  --channel-id <CHANNEL_ID> \
  --space-id   <SPACE_ID> \
  --base-url   <PLATFORM_BASE_URL>
```

The subprocess inherits these environment variables from the saved config:
`DOMYN_API_KEY`, `VLLM_API_KEY`, `VLLM_BASE_URL`, `VLLM_MODEL`.

Returns `{"status": "started", "pid": 1234}` or `{"status": "already_running", "pid": 1234}`.

### POST /stop

Sends SIGTERM to the running process (SIGKILL after 10 s if it does not exit).

Returns `{"status": "stopped"}` or `{"status": "not_running"}`.

### GET /status

```json
{"status": "running", "pid": 1234}
{"status": "not_running"}
{"status": "exited", "exit_code": 0}
```

---

## Local setup

**Prerequisites**: `domyn` CLI available in PATH (installed via `domyn_agents` wheel).

```bash
# Install dependencies
pip install fastapi "uvicorn[standard]" pydantic

# Point the service at the agent directory
export AGENT_WORKDIR=/path/to/service-deploy/services/langgraph_agent_example

# Start the controller
uvicorn main:app --host 0.0.0.0 --port 8080

# Configure the agent
curl -X POST http://localhost:8080/update \
  -H "Content-Type: application/json" \
  -d '{
    "domyn_api_key": "domyn_xxx",
    "channel_id": "abc123",
    "space_id": "uuid-here",
    "platform_base_url": "qa.crystal.io",
    "vllm_api_key": "sk-xxx",
    "vllm_base_url": "https://gateway-dev.llm.crystal.ai/v1",
    "vllm_model": "Qwen/Qwen3-32B"
  }'

# Start the agent
curl -X POST http://localhost:8080/start

# Stop the agent
curl -X POST http://localhost:8080/stop
```

---

## Docker setup

**Step 1** — Copy the `domyn_agents` wheel into the `wheels/` directory:

```bash
cp ../langgraph_agent_example/wheels/domyn_agents-*.whl wheels/
```

**Step 2** — Build and run:

```bash
docker compose up -d
```

The container exposes the API on port **9081** and mounts `../langgraph_agent_example` as the agent working directory (`/srv/agent`), so `agent_expose.py` is automatically available to the subprocess.

```bash
docker compose logs -f   # follow logs
docker compose down      # stop and remove
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_WORKDIR` | `.` | Working directory where `agent_expose.py` lives |

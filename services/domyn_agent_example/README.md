# Domyn Platform — Native domyn-agents ReAct Agent Blueprint

A ready-to-run example of a native domyn-agents ReAct agent connected to the Domyn platform as a subagent. The agent uses an LLM (via a vLLM-compatible endpoint) and a set of built-in tools to answer tasks sent by the platform orchestrator.

---

## What's included

```
domyn_agent_example/
├── agent_expose.py        # The agent definition — modify tools and LLM config here
├── test_local.py          # Run the agent locally without a WebSocket connection
├── Dockerfile             # Container image definition
├── docker-compose.yml     # One-command local Docker run
├── requirements.txt       # Python dependencies (excl. domyn-agents wheel)
├── .env.example           # Required environment variables
└── wheels/                # Place the domyn-agents .whl file here
```

---

## Prerequisites

- Python 3.11+ (for local/laptop runs)
- Docker (for containerised runs and VM deployment)
- The `domyn-agents` wheel file — place it in `wheels/`

---

## Step 0 — Prepare the wheel

Obtain the `domyn_agents-*.whl` file and place it inside the `wheels/` directory before running anything:

```bash
ls wheels/
```

---

## Step 1 — Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in your values
```

| Variable | Description |
|---|---|
| `DOMYN_API_KEY` | API key from the Domyn platform |
| `DOMYN_CHANNEL_ID` | WebSocket channel ID assigned to this subagent |
| `DOMYN_SPACE_ID` | Your space ID on the platform |
| `DOMYN_BASE_URL` | Platform base URL |
| `VLLM_API_KEY` | API key for the vLLM/LLM gateway |
| `VLLM_BASE_URL` | Base URL of the LLM gateway (OpenAI-compatible, full path to `/v1/chat/completions`) |
| `VLLM_MODEL` | Model name to use (e.g. `Qwen/Qwen3-32B`) |

---

## Running locally (laptop)

Install dependencies:

```bash
pip install wheels/domyn_agents-*.whl
```

Test the agent without any platform connection:

```bash
python test_local.py
# or with a custom task:
python test_local.py "Add 5 and 7"
```

Connect to the platform:

```bash
source .env
domyn expose agent_expose:agent \
    --channel-id  $DOMYN_CHANNEL_ID \
    --space-id    $DOMYN_SPACE_ID \
    --base-url    $DOMYN_BASE_URL
```

`domyn expose` accepts a `module:symbol` argument pointing to a domyn `Agent` instance. `agent_expose` is the Python module (i.e. `agent_expose.py`) and `agent` is the `Agent` instance exported from it.

The process stays running and reconnects automatically on network drops.

---

## Running with Docker (laptop or VM)

Build the image:

```bash
docker build -t domyn-agent-blueprint .
```

Run (reads credentials from `.env`):

```bash
docker run --env-file .env domyn-agent-blueprint
```

Or with Docker Compose (one command):

```bash
docker compose up
```

---

## Deploying to a VM

1. Copy the blueprint directory to your VM:

```bash
scp -r services/domyn_agent_example/ user@your-vm:/opt/domyn-agent/
```

2. SSH into the VM and build:

```bash
ssh user@your-vm
cd /opt/domyn-agent
cp .env.example .env && nano .env   # fill in credentials
docker build -t domyn-agent-blueprint .
```

3. Run as a systemd service for automatic restart on reboot:

```ini
# /etc/systemd/system/domyn-agent.service
[Unit]
Description=Domyn Native Agent Subagent
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker run --rm --env-file /opt/domyn-agent/.env \
    --name domyn-agent domyn-agent-blueprint
ExecStop=/usr/bin/docker stop domyn-agent

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now domyn-agent
sudo journalctl -fu domyn-agent   # tail logs
```

---

## Agent overview

The agent is a domyn-agents ReAct agent backed by an OpenAI-compatible LLM. It receives a task from the platform orchestrator and reasons over a set of tools to produce a response.

### Built-in tools

| Tool | Description |
|---|---|
| `add_numbers` | Add two numbers |
| `multiply_numbers` | Multiply two numbers |
| `get_current_time` | Return the current UTC time |
| `reverse_string` | Reverse a string |
| `count_words` | Count words in a string |

### Adding tools

Open `agent_expose.py` and add a tool to the agent:

```python
from domyn_agents.core.decorators import tool

@tool(name="my_tool", description="Description shown to the LLM.")
def my_tool(x: str) -> str:
    return x.upper()

agent = Agent(
    ...
    tools=[..., my_tool],
)
```

### Changing the LLM

Edit `_get_llm()` in `agent_expose.py` or set the env vars `VLLM_MODEL`, `VLLM_BASE_URL`, `VLLM_API_KEY`.

The `OpenAIProvider` accepts any OpenAI-compatible endpoint (vLLM, Together, Groq, etc.).

---

## How it works

```
Platform orchestrator
        │
        │  AGENT_START (via WebSocket relay)
        ▼
domyn expose agent_expose:agent
        │
        │  Receives AGENT_START, extracts task text
        │  Runs domyn Runner with the Agent
        │
        ▼
Agent ReAct loop
        │
        ├── LLM call (VLLM_MODEL via VLLM_BASE_URL)
        ├── Tool execution (local)
        └── RESPONSE → streamed back to platform
```

The `domyn expose` command auto-detects that `agent_expose:agent` is a domyn `Agent` instance and uses the `DomynAgentRuntime` — no input mapper or LangChain callbacks required.

Multi-turn conversations are supported: the agent maintains conversation history per `conversation_id` across calls.

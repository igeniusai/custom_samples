# Domyn Platform — LangGraph ReAct Agent Blueprint

A ready-to-run example of a LangGraph ReAct agent connected to the Domyn platform as a subagent. The agent uses an LLM (via a vLLM-compatible endpoint) and a set of built-in tools to answer tasks sent by the platform orchestrator.

---

## What's included

```
blueprint/langgraph_agent/
├── agent_expose.py        # The agent graph — modify tools and LLM config here
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
| `DOMYN_CONFIGURATION_ID` | (Optional) Platform configuration ID; targets a specific configuration when fetching delegate tools |
| `DOMYN_BASE_URL` | Platform base URL |
| `VLLM_API_KEY` | API key for the vLLM/LLM gateway |
| `VLLM_BASE_URL` | Base URL of the LLM gateway (OpenAI-compatible) |
| `VLLM_MODEL` | Model name to use (e.g. `Qwen/Qwen3-32B`) |

---

## Running locally (laptop)

Install dependencies:

```bash
pip install wheels/domyn_agents-*.whl -r requirements.txt
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
domyn expose agent_expose:graph \
    --framework   langgraph \
    --channel-id  $DOMYN_CHANNEL_ID \
    --space-id    $DOMYN_SPACE_ID \
    --base-url    $DOMYN_BASE_URL
```

`domyn expose` accepts a `module:symbol` argument pointing to a compiled LangGraph graph object. `agent_expose` is the Python module (i.e. `agent_expose.py`) and `graph` is the compiled graph instance exported from it. Any LangGraph graph can be served this way — change the argument to point to a different module or symbol as needed.

The process stays running and reconnects automatically on network drops.

---

## Running with Docker (laptop or VM)

Build the image:

```bash
docker build -t langgraph-agent-blueprint .
```

Run (reads credentials from `.env`):

```bash
docker run --env-file .env langgraph-agent-blueprint
```

Or with Docker Compose (one command):

```bash
docker compose up
```

---

## Deploying to a VM

1. Copy the blueprint directory to your VM:

```bash
scp -r blueprint/langgraph_agent/ user@your-vm:/opt/langgraph-agent/
```

2. SSH into the VM and build:

```bash
ssh user@your-vm
cd /opt/langgraph-agent
cp .env.example .env && nano .env   # fill in credentials
docker build -t langgraph-agent-blueprint .
```

3. Run as a systemd service for automatic restart on reboot:

```ini
# /etc/systemd/system/langgraph-agent.service
[Unit]
Description=Domyn LangGraph Agent Subagent
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker run --rm --env-file /opt/langgraph-agent/.env \
    --name langgraph-agent langgraph-agent-blueprint
ExecStop=/usr/bin/docker stop langgraph-agent

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now langgraph-agent
sudo journalctl -fu langgraph-agent   # tail logs
```

---

## Agent overview

The agent is a LangGraph ReAct graph backed by an OpenAI-compatible LLM. It receives a `task` string from the platform orchestrator and reasons over a set of tools to produce a response.

### Built-in tools

| Tool | Description |
|---|---|
| `add_numbers` | Add two numbers |
| `multiply_numbers` | Multiply two numbers |
| `get_current_time` | Return the current UTC time |
| `reverse_string` | Reverse a string |
| `count_words` | Count words in a string |

### Platform tools (governed by the Domyn platform)

| Tool | Description |
|---|---|
| `web_search` | Search the web |
| `search_papers_arxiv` | Search academic papers on arXiv |

Platform tools are tools you connect to your agent through the Domyn platform canvas. The workflow is:

1. On the Domyn platform, create a **delegate agent** — this gives you a `DOMYN_CHANNEL_ID`.
2. From the canvas, attach the platform tools you want (e.g. `web_search`) to that channel.
3. At startup, the blueprint fetches whichever tools are connected to the channel and adds them to `LOCAL_TOOLS` alongside the built-in tools.

If no platform credentials are set, or the agent has not been connected to a channel yet, the blueprint starts normally with local tools only — no error is raised.

### Adding tools

Open `agent_expose.py` and add your tool to `LOCAL_TOOLS`:

```python
@tool
def my_tool(x: str) -> str:
    """Description shown to the LLM."""
    return x.upper()

LOCAL_TOOLS = [
    ...
    my_tool,
]
```

### Changing the LLM

Edit `_get_llm()` in `agent_expose.py` or set the env vars `VLLM_MODEL`, `VLLM_BASE_URL`, `VLLM_API_KEY`.

---

## Input format

The platform orchestrator sends the user message as a string under the `task` key. The agent receives it as a standard user message and responds with its final answer.

Example task:

```
Add 5 and 7
```

Expected response:

```
The result of adding 5 and 7 is 12.
```

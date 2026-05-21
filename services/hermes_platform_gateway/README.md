# hermes-platform-gateway — deploy blueprint

A self-contained Docker deployment of [hermes-agent](https://github.com/NousResearch/hermes-agent) wired to the Domyn platform through the `hermes-platform-gateway` plugin. One container, one `docker compose up`, and a hermes worker shows up on your canvas, ready to receive `AGENT_START` events from the relay and reply over the same WebSocket.

## Layout

```
hermes_platform_gateway/
├── Dockerfile              # Builds hermes + plugin + manifest into one image
├── docker-compose.yml      # One-command run, env vars from .env
├── Makefile                # build / up / down / logs / shell / clean
├── requirements.txt        # Extra runtime deps (httpx, websockets)
├── .env.example            # Copy to .env and fill in
├── wheels/                 # Drop `domyn_agents-*.whl` here before building
└── plugins/
    └── hermes-platform-gateway/   # Vendored plugin source + manifest
```

## How it fits together

1. The Dockerfile installs hermes-agent from git, the `domyn-agents` wheel, then `pip install /opt/hermes-platform-gateway` so `hermes_platform_gateway` is importable.
2. The same plugin folder is *also* copied under `$HERMES_HOME/plugins/hermes_platform_gateway/` so hermes' plugin loader picks up `plugin.yaml` and calls `register(ctx)`.
3. `config.yaml` opt-ins the plugin under `plugins.enabled` — standalone-kind plugins are skipped otherwise.
4. On startup, `register(ctx)`:
   - POSTs `https://api.<DOMYN_BASE_URL>/api/agents-service/tool/list_delegate_tools_for_channel` to discover canvas tools (uses the `api.` subdomain — the same shape `domyn expose` uses).
   - Registers each tool into hermes' `platform` toolset with a sync handler that forwards calls over the relay WebSocket.
   - Opens `wss://<DOMYN_BASE_URL>/relay/v1/ws` with `api-key` / `space-id` / `channel-id` headers, and runs a background daemon thread that:
     - injects platform `AGENT_START` events into hermes via `ctx.inject_message`,
     - streams tokens back as `RESPONSE(is_partial=True)` events,
     - sends `AGENT_END` after each LLM turn,
     - resolves outstanding `TOOL_END`/`TOOL_ERROR` to the matching `concurrent.futures.Future` by `call_id`.

## Prerequisites

- Docker + Docker Compose
- A `domyn_agents-*.whl` wheel — required for relay event models. Build it once from the `domyn-agents` repo and drop into `wheels/`:

  ```bash
  cd /path/to/domyn-agents && uv build --wheel --out-dir /tmp/dist
  cp /tmp/dist/domyn_agents-*.whl wheels/
  ```
- A vLLM-compatible LLM gateway (URL + API key)
- Domyn platform credentials with **worker-role** access for the channel (a read-only HTTP api-key passes tool discovery but the WS relay rejects it with `4401 Unauthorized`).

## Configure

```bash
cp .env.example .env
$EDITOR .env       # fill in DOMYN_* and VLLM_*
```

| Variable | Required | Purpose |
|---|---|---|
| `DOMYN_API_KEY` | Yes | Worker key — used for both HTTP discovery and WS auth |
| `DOMYN_BASE_URL` | Yes | Platform host (`conv2.crystal.io` or `https://conv2.crystal.io`) |
| `DOMYN_SPACE_ID` | Yes | Space scope |
| `DOMYN_CHANNEL_ID` | Yes | Relay channel for this worker |
| `DOMYN_CONFIGURATION_ID` | No | Pin to a specific configuration (omit for active) |
| `PLATFORM_TOOL_TIMEOUT` | No | Per-tool timeout, default 120s |
| `PLATFORM_TOOL_REFRESH_INTERVAL` | No | Canvas poll interval, default 60s (0 disables) |
| `VLLM_API_KEY` | Yes | Hermes' LLM provider auth |
| `VLLM_BASE_URL` | Yes | OpenAI-compatible LLM endpoint |
| `VLLM_MODEL` | Yes | Model name |
| `HERMES_PLUGINS_DEBUG` | No | `1` surfaces plugin-discovery debug logs |

## Build & run

```bash
make build       # docker compose build
make up          # docker compose up -d
make logs        # tail logs — look for "registered N platform tool(s)"
```

The first time you `up` the container, the logs should show:

```
Plugin hermes_platform_gateway registered tool: <your_tool_name>
platform-gateway: registered 1 platform tool(s)
```

Send a chat message from the canvas and you should see `AGENT_START` / `TOOL_START` / `TOOL_END` / `AGENT_END` events flow through.

## Updating the worker code

The plugin under `plugins/hermes-platform-gateway/` is vendored verbatim from the upstream repo. To pick up upstream changes:

```bash
cp -R /path/to/hermes-platform-gateway/{hermes_platform_gateway,pyproject.toml,README.md} \
      plugins/hermes-platform-gateway/
make build && make up
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Container logs: `4401 Unauthorized` on WS connect | `DOMYN_API_KEY` lacks worker-role scope on this channel. Regenerate it from the platform with worker permissions. |
| Logs say `registered 0 platform tool(s)` | Canvas has no tools attached, or `DOMYN_CHANNEL_ID` points at the wrong channel. Verify with `curl https://api.<DOMYN_BASE_URL>/api/agents-service/tool/list_delegate_tools_for_channel -H 'api-key: …' -d '{"space_id":"…","channel_id":"…","configuration_id":null}'`. |
| Two workers responding to the same message | Multiple containers/processes are subscribed to the same `channel-id`. Only one worker should subscribe per channel. |
| Discovery returns tools but WS reconnects in a tight loop | Same as above — relay kicks each subscriber off when another connects. |

## Stopping

```bash
make down        # stops the container, keeps the hermes-home volume
make clean       # also removes the image + volume
```

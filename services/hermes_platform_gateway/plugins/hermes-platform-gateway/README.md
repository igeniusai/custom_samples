# hermes-platform-gateway

A hermes-agent pip plugin that dynamically registers canvas-connected tools at startup. No per-canvas YAML files or shell commands required — tools are discovered from the platform and forwarded over the relay WebSocket using the same `TOOL_START`/`TOOL_END` protocol as `domyn expose`.

---

## How it works

1. **Tool discovery** — on startup, the plugin calls `POST /api/agents-service/tool/list_delegate_tools_for_channel` (on the `api.` subdomain, matching `domyn expose`) to fetch the tools currently connected on the canvas for the given `space_id` + `channel_id` (and optional `configuration_id`).
2. **Schema conversion** — platform parameter lists are translated to hermes JSON Schema objects and registered with `ctx.register_tool`.
3. **Relay connection** — a background daemon thread opens `wss://{DOMYN_BASE_URL}/relay/v1/ws` with the auth headers (`channel-id`, `space-id`, `api-key`).
4. **Tool call flow** — when hermes invokes a platform tool, the handler sends a `TOOL_START` relay message and blocks on a `concurrent.futures.Future` until the matching `TOOL_END` (keyed by `call_id`) resolves it.
5. **Reconnection** — if the WebSocket drops, in-flight calls fail immediately with an error JSON and the background loop reconnects with full-jitter exponential backoff.
6. **Canvas changes** — a `RefreshLoop` daemon thread polls the tool list every `PLATFORM_TOOL_REFRESH_INTERVAL` seconds (default 60). New tools are registered, removed tools are deregistered, unchanged tools are left alone.
7. **Inbound user input** — when the platform sends an `AGENT_START` relay event, the plugin extracts the user text and injects it into hermes via `ctx.inject_message`, triggering a normal agent turn.
8. **Turn completion** — after each LLM turn (`post_llm_call` hook), the plugin sends one `AGENT_END` relay event carrying the full assistant response and the correlation IDs (`author`, `interaction_id`, `turn_id`, `conversation_id`) from the originating `AGENT_START`. We intentionally do *not* stream tokens as `RESPONSE(is_partial=True)` events: the platform treats each `RESPONSE` as its own block (joined with newlines in the UI) and a non-empty `AGENT_END` is "promoted" to a final `RESPONSE` — mixing the two paths produces duplicated output. The current shape mirrors what `domyn expose`'s Runtime does.

---

## Prerequisites

- Python 3.11+
- hermes-agent installed
- `domyn-agents` installed (editable install from the local repo — see Installation)

---

## Installation

The plugin manifest (`plugin.yaml` + `__init__.py`) lives in `~/.hermes/plugins/hermes_platform_gateway/`, but `register()` imports the actual implementation (`fetch_tools`, `GatewayConnection`, …) from the pip-installed `hermes_platform_gateway` package — so you must install **into the hermes-agent venv**, not whichever Python happens to be on `$PATH`:

```bash
HERMES_VENV=~/.hermes/hermes-agent/venv

# Plugin + dev deps (editable so local changes take effect immediately)
VIRTUAL_ENV=$HERMES_VENV uv pip install --python $HERMES_VENV/bin/python \
    -e /path/to/hermes-platform-gateway

# domyn-agents — required for event models (RelayMessage, BaseEvent, etc.)
VIRTUAL_ENV=$HERMES_VENV uv pip install --python $HERMES_VENV/bin/python \
    -e /path/to/domyn-agents
```

Then mirror the manifest + `__init__.py` into `~/.hermes/plugins/hermes_platform_gateway/` (the plugin loader scans that directory for `plugin.yaml`).

**Enable the plugin** in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - platform-gateway
```

The plugin is opt-in. hermes will silently ignore it if this line is absent.

---

## Configuration

All configuration is via environment variables injected before hermes starts (typically by a sandbox supervisor):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DOMYN_API_KEY` | Yes | — | Auth for HTTP tool discovery and WebSocket handshake |
| `DOMYN_BASE_URL` | Yes | — | Platform host, no scheme — bare hostname like `conv2.crystal.io` (the plugin prepends `api.` for HTTP, mirrors `domyn expose`) |
| `DOMYN_SPACE_ID` | Yes | — | Scopes tool discovery to a specific canvas |
| `DOMYN_CHANNEL_ID` | Yes | — | WebSocket relay channel + body field on the discovery POST |
| `DOMYN_CONFIGURATION_ID` | No | — | Pin discovery to a specific configuration (omit for active) |
| `PLATFORM_TOOL_TIMEOUT` | No | `120` | Per-call timeout in seconds |
| `PLATFORM_TOOL_REFRESH_INTERVAL` | No | `60` | Canvas poll interval in seconds; set to `0` to disable |

If any required variable is missing, the plugin logs a warning and hermes starts with zero platform tools (fail-open).

---

## Quickstart — local stub

`stub_platform.py` simulates the platform relay on `localhost:9999`. It serves the HTTP tool list and handles WebSocket tool calls.

### 1. Install dependencies

```bash
cd /path/to/hermes-platform-gateway
uv pip install -e ".[dev]"
```

### 2. Start the stub

```bash
uv run python stub_platform.py
```

Expected output:
```
[stub] Listening on http://localhost:9999
[stub] WebSocket at ws://localhost:9999/relay/v1/ws
```

The stub exposes one tool: `echo` — it returns `"echo: <message>"` for any `message` argument.

### 3. Verify the tool list endpoint

```bash
curl -s -X POST http://localhost:9999/api/agents-service/tool/list_from_config \
  -H "Content-Type: application/json" \
  -d '{"space_id": "s1"}' | python -m json.tool
```

Expected:
```json
[
    {
        "name": "echo",
        "description": "Echo the input message back",
        "parameters": [
            {
                "name": "message",
                "type": "str",
                "is_required": true,
                "description": "The message to echo"
            }
        ]
    }
]
```

### 4. Run hermes with platform tools

Open a second terminal:

```bash
DOMYN_API_KEY=test \
DOMYN_BASE_URL=localhost:9999 \
DOMYN_SPACE_ID=s1 \
DOMYN_CHANNEL_ID=c1 \
hermes
```

At startup you should see a log line like:
```
platform-gateway: registered 1 platform tool(s)
```

### 5. Invoke the platform tool

Ask hermes to use it:

```
> Use the echo tool with message "hello"
```

In the stub terminal you will see:
```
[stub] TOOL_START  tool=echo  params={'message': 'hello'}  call_id=<uuid>
[stub] TOOL_END    observation='echo: hello'
```

hermes receives the result and replies with it.

---

## Connecting to the real platform

Set the env vars to point at your actual platform:

```bash
DOMYN_API_KEY=<your-api-key> \
DOMYN_BASE_URL=api.yourdomain.com \
DOMYN_SPACE_ID=<space-id> \
DOMYN_CHANNEL_ID=<channel-id> \
hermes
```

`DOMYN_BASE_URL` is a bare hostname (with optional port). The plugin uses `wss://` for remote hosts and `ws://` for localhost. Tool discovery uses `https://` / `http://` by the same rule.

---

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run --active pytest tests/ -v

# Run a single file
uv run --active pytest tests/test_gateway.py -v
```

Test files:

| File | What it covers |
|---|---|
| `tests/test_schema.py` | `convert_schema()` — type mapping, required/optional/default, unknown types |
| `tests/test_client.py` | `fetch_tools()` HTTP requests, `build_ws_url()` scheme selection |
| `tests/test_gateway.py` | `GatewayConnection` internals — receive loop, fail-pending, call_tool round-trip, `_serialize_observation` |
| `tests/test_register.py` | `register(ctx)` — env var checks, schema wiring, handler delegation, correct WS URL and headers |
| `tests/test_integration.py` | End-to-end against a real in-process stub — tool discovery, TOOL_START/END round-trip, inbound AGENT_START, outbound send_event, auth headers |

---

## Protocol reference

### Tool discovery (HTTP)

```
POST https://api.{DOMYN_BASE_URL}/api/agents-service/tool/list_delegate_tools_for_channel
Headers: api-key: {DOMYN_API_KEY}
         Content-Type: application/json
Body:    {
           "space_id":         "{DOMYN_SPACE_ID}",
           "channel_id":       "{DOMYN_CHANNEL_ID}",
           "configuration_id": "{DOMYN_CONFIGURATION_ID}"  // null when unset
         }
```

Response: a JSON array of tool definitions, or `{"tools": [...]}`.

### Tool call (WebSocket)

**Outbound (hermes → platform):**
```json
{
  "meta": {},
  "payload": {
    "event_type": "tool_start",
    "author": "hermes",
    "action": {
      "type": "ToolAction",
      "name": "send_email",
      "parameters": {"to": "user@example.com"},
      "call_id": "<uuid>"
    }
  }
}
```

**Inbound (platform → hermes):**
```json
{
  "meta": {},
  "payload": {
    "event_type": "tool_end",
    "author": "platform",
    "action": {
      "type": "ToolAction",
      "name": "send_email",
      "call_id": "<same-uuid>",
      "observation": "Email sent successfully"
    }
  }
}
```

The `call_id` on `TOOL_END` / `TOOL_ERROR` resolves the matching in-flight `concurrent.futures.Future`. On `TOOL_ERROR`, the future is rejected and the handler returns `{"error": "<error_message>"}`.

### Bidirectional relay (platform → hermes)

**Inbound user turn (`AGENT_START`):**
```json
{
  "meta": {},
  "payload": {
    "event_type": "agent_start",
    "author": "platform",
    "interaction_id": "<uuid>",
    "turn_id": "<uuid>",
    "action": {
      "type": "AgentAction",
      "name": "invoke",
      "parameters": {"input": "What is the weather?"}
    }
  }
}
```

**Outbound streaming token (`RESPONSE`):**
```json
{
  "meta": {},
  "payload": {
    "event_type": "response",
    "author": "platform",
    "interaction_id": "<same-uuid>",
    "turn_id": "<same-uuid>",
    "is_partial": true,
    "content": [{"type": "Part", "text": "The weather"}]
  }
}
```

**Outbound turn complete (`AGENT_END`):**
```json
{
  "meta": {},
  "payload": {
    "event_type": "agent_end",
    "author": "platform",
    "interaction_id": "<same-uuid>",
    "turn_id": "<same-uuid>",
    "content": [{"type": "Part", "text": "The weather is sunny."}]
  }
}
```

`interaction_id` and `turn_id` are copied from the originating `AGENT_START` so the platform can correlate streaming fragments with the triggering request.

### WebSocket auth headers

```
channel-id: {DOMYN_CHANNEL_ID}
space-id:   {DOMYN_SPACE_ID}
api-key:    {DOMYN_API_KEY}
```

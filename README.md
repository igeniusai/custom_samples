# custom_samples

Ready-to-use service blueprints for the Domyn platform.

| Service | Description |
|---|---|
| [custom_ui_guardrail](services/custom_ui_guardrail/) | Dual LLM-based guardrail with admin UI and verdict history |
| [langgraph_agent_example](services/langgraph_agent_example/) | LangGraph ReAct agent connected to Domyn as a subagent |

---

## Custom UI Guardrail

> Full documentation: [services/custom_ui_guardrail/README.md](services/custom_ui_guardrail/README.md)

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
cd services/custom_ui_guardrail

# Install dependencies
make install

# Start the server (hot-reload, port 8080)
make dev
```

### Expose publicly

Pick one option to make the local server reachable from the internet.

**Cloudflare Tunnel** — [install cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
```bash
cloudflared tunnel --url localhost:8080
```

**ngrok** — [install ngrok](https://ngrok.com/downloads)
```bash
ngrok http 8080
```

Both print a public HTTPS URL you can register as a hook endpoint in the Domyn platform.

---

## LangGraph Agent Example

> Full documentation: [services/langgraph_agent_example/README.md](services/langgraph_agent_example/README.md)

Requires [Docker](https://docs.docker.com/get-docker/) with the Compose plugin.

```bash
cd services/langgraph_agent_example
docker compose up --build
```


# Domyn Platform - Custom Samples

Ready-to-use samples showing how to develop custom guardrails and custom agents for the Domyn Platform.

| Sample | Type | Description |
|---|---|---|
| [Minimal guardrail](services/minimal_guardrail/) | Guardrail | Simple deterministic guardrail |
| [LLM guardrail with custom UI](services/custom_ui_guardrail/) | Guardrail | Dual LLM-based guardrail with admin UI and verdict history |
| [Minimal LangGraph agent](services/langgraph_deterministic_graph_example/) | Agent | Deterministic LangGraph graph connected to Domyn as a subagent |
| [LangGraph ReAct agent](services/langgraph_agent_example/) | Agent | LangGraph ReAct agent connected to Domyn as a subagent |

---

## Production deployment

This README is focused on interactive development.

For detailed instructions on how to deploy the services to a production cluster, follow [DEPLOYMENT.md](DEPLOYMENT.md).

> **NOTE:** The Domyn Platform will take care of most of the production deployment steps in future releases.

---

## Custom LLM guardrail

A ready-to-run guardrail service for the Domyn platform. Exposes two independent LLM-based guardrail hooks — one for user inputs, one for agent responses — each with its own configurable policy and admin UI embedded directly in the platform canvas.

> Full documentation at [services/custom_ui_guardrail/README.md](services/custom_ui_guardrail/README.md)

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

## LangGraph ReAct agent

A ready-to-run example of a LangGraph ReAct agent connected to the Domyn platform as a subagent. The agent uses an LLM (via a vLLM-compatible endpoint) and a set of built-in tools to answer tasks sent by the platform orchestrator.

> Full documentation at [services/langgraph_agent_example/README.md](services/langgraph_agent_example/README.md)

Requires [Docker](https://docs.docker.com/get-docker/)

```bash
cd services/langgraph_agent_example
docker compose up --build
```


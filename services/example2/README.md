# MCP Integration Sample for Domyn

This project is a **hands-on sample** showing how to build an MCP server that integrates with the Domyn platform. The domain (ESG investment analysis) was chosen to provide a relatable context — it is not meant to be production-grade. Use it as a starting point to understand MCP integration patterns and adapt them to your own use case.

## What this sample demonstrates

| Capability | Where to look |
|---|---|
| **Creating an MCP server** | `src/mcpesg/app.py` — FastAPI + [FastMCP](https://github.com/jlowin/fastmcp) setup with stateless HTTP transport |
| **Defining MCP tools** | `src/mcpesg/interfaces/mcp/esg.py` — tool registration with descriptions, parameter schemas, and annotations |
| **Calling external APIs from a tool** | `src/mcpesg/use_cases/esg.py` — Yahoo Finance (`yfinance`) for company data, NZDPU API for carbon emissions |
| **Working with data inside a tool** | `src/mcpesg/use_cases/esg.py` — in-memory datasets, weighted calculations, caching with TTL |
| **Serving static files for chat rendering** | `src/mcpesg/app.py` + `statics/` — Plotly charts exported as PNGs and served via FastAPI so the chat can render them inline |
| **Exposing REST endpoints alongside MCP** | `src/mcpesg/interfaces/rest/esg.py` — same logic available as GET endpoints for easy testing outside an MCP client |
| **Local dev with public tunnel** | `Makefile` + `entrypoint.sh` — run locally with hot-reload and expose via serveo.net to connect from the Domyn platform |

## MCP tools exposed

The server registers 7 tools on the `/mcp/` endpoint:

| Tool | Purpose |
|---|---|
| `esg_list_portfolios` | List available sample portfolios |
| `esg_get_portfolio` | Get holdings detail for a portfolio |
| `esg_get_scores` | Fetch ESG risk scores (Sustainalytics-based) for a portfolio or arbitrary tickers |
| `esg_compare_portfolios` | Compare two portfolios across E/S/G dimensions with a radar chart |
| `esg_carbon_footprint` | Calculate weighted-average carbon intensity (WACI) with benchmark comparison and bar chart |
| `esg_suggest_replacements` | Suggest lower-risk ESG alternatives for portfolio holdings |
| `esg_check_sfdr` | Assess EU SFDR classification (Article 6/8/9) with gap analysis |

## Project structure

```
src/mcpesg/
  app.py                    # FastAPI + FastMCP app factory, static file serving
  config.py                 # Settings (env-driven, Pydantic)
  main.py / main_dev.py     # Entry points (prod / hot-reload)
  interfaces/
    mcp/esg.py              # MCP tool definitions
    rest/esg.py             # REST endpoint wrappers
  use_cases/
    esg.py                  # Domain logic, external API calls, chart generation
tests/
  test_esg_use_case.py      # Smoke tests for all tools
statics/                    # Generated chart images (served at /statics/)
```

## Getting started

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

```sh
make install   # install dependencies
make run       # start the server on http://localhost:8080
```

For hot-reload during development:

```sh
make run-dev
```

### Expose to the Domyn platform

> **Note:** serveo.net is the built-in tunnel solution used by this project, but it is entirely optional. If you prefer a different tunnelling tool (e.g. [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/), [localtunnel](https://theboroer.github.io/localtunnel-www/), …), simply run:
>
> ```sh
> make install   # install dependencies (only once)
> make run       # start the server on http://localhost:8080
> ```
>
> Then use your preferred tool to expose port `8080` externally. The MCP endpoint will be at `<your-public-url>/mcp/`.

> **Important:** whenever the server is accessed through an external URL (regardless of the tunnelling tool), you must set the `BASE_EXPOSED_URL` environment variable to that URL. The server uses it to build the absolute links to chart images returned by the tools. Without it, images will not render correctly in the chat.
>
> Example using serveo with a random subdomain — open two terminals:
>
> **Terminal 1** — start the tunnel and note the assigned URL:
> ```sh
> make expose-random
> # serveo will print something like:
> # Forwarding HTTP traffic from https://abc123.serveousercontent.com
> ```
>
> **Terminal 2** — start the server with that URL:
> ```sh
> BASE_EXPOSED_URL=https://abc123.serveousercontent.com make run
> ```

Replace the command in the terminal 1 with your prefered tunnelling tool.

---

The built-in tunnel is powered by **[serveo.net](https://serveo.net)**, a free SSH-based reverse proxy. Before using this feature you need to:

1. **Register** at [serveo.net](https://serveo.net) and create an SSH key pair for your account.
2. **Save the private key** in the project root with the name `serveo_key` (no extension).
3. Make sure the file has the correct permissions: `chmod 600 serveo_key`.

Once the key is in place, start the tunnel:

```sh
make expose
```

The MCP endpoint will be reachable at `https://mcp.serveousercontent.com/mcp/`.

To use a custom subdomain:

```sh
SERVEO_SUBDOMAIN=mysubdomain make expose
```

### Docker

```sh
make docker-build          # build the image
make docker-run            # server only (localhost:8080)
make docker-run-exposed    # server + serveo tunnel (work with a key)
```

### Tests

```sh
uv run pytest tests/ -v
```

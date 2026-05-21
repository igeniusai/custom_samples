FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HERMES_HOME=/root/.hermes \
    HERMES_PLUGINS_DEBUG=0

WORKDIR /app

# Build tools needed for a few transitive C extensions hermes pulls in.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 1) Runtime Python deps.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) hermes-agent — installed from source (no PyPI release).
#    Override at build time: `docker compose build --build-arg HERMES_REF=v0.14.0`.
ARG HERMES_REF=main
RUN pip install --no-cache-dir \
        "git+https://github.com/NousResearch/hermes-agent.git@${HERMES_REF}#egg=hermes-agent"

# 3) domyn-agents — required by the gateway plugin for relay event models.
#    Bundled as a wheel under ./wheels so the build doesn't need the private
#    igenius PyPI index.
COPY wheels/ wheels/
RUN pip install --no-cache-dir wheels/domyn_agents-*.whl

# 4) hermes-platform-gateway plugin. Two installs are needed:
#    - The pip package goes into site-packages so the plugin's
#      `from hermes_platform_gateway.client import …` imports resolve.
#    - The manifest + __init__.py are also dropped under $HERMES_HOME/plugins
#      so hermes' discovery sees a `plugin.yaml` and calls `register(ctx)`.
COPY plugins/hermes-platform-gateway/ /opt/hermes-platform-gateway/
RUN pip install --no-cache-dir /opt/hermes-platform-gateway && \
    mkdir -p ${HERMES_HOME}/plugins/hermes_platform_gateway && \
    cp /opt/hermes-platform-gateway/hermes_platform_gateway/*.py \
       ${HERMES_HOME}/plugins/hermes_platform_gateway/ && \
    cp /opt/hermes-platform-gateway/plugin.yaml \
       ${HERMES_HOME}/plugins/hermes_platform_gateway/

# 5) hermes config:
#    - point hermes' default model at the vLLM gateway (api_key + base_url +
#      model come from env vars at startup via hermes' ${VAR} expansion);
#    - opt-in the platform-gateway plugin — standalone-kind plugins are
#      skipped unless explicitly listed under `plugins.enabled`.
COPY hermes-config.yaml ${HERMES_HOME}/config.yaml

# 6) Run hermes as a relay-attached worker. Stdin is closed in containers,
#    so we drop into `hermes chat` non-interactively — the plugin's
#    `on_session_start` hook will still fire, the WS subscriber stays open
#    in a daemon thread, and AGENT_START events injected from the platform
#    drive the conversation.
CMD ["hermes", "chat"]

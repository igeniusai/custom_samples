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

# 5) i18n catalog — upstream hermes' pip install does NOT package its
#    locales/ directory, so every t() call falls back to the raw key
#    (you'd see "gateway.approve.session_singular" rendered verbatim in
#    chat replies to /approve). We drop our own minimal en.yaml next to
#    the installed agent/ package so agent.i18n._locales_dir() finds it.
COPY locales/en.yaml /usr/local/lib/python3.11/site-packages/locales/en.yaml

# 6) hermes config template + entrypoint that materialises it.
#    gateway mode reads ~/.hermes/config.yaml via read_raw_config() which
#    does NOT expand ${VAR} references — so we resolve them at container
#    start with entrypoint.sh and write the result into $HERMES_HOME.
COPY hermes-config.yaml /opt/hermes-config.template.yaml
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 7) Run hermes in gateway mode. The gateway is the headless, multi-session
#    runner — it doesn't open a TUI and doesn't need a TTY. AGENT_START
#    events for any conversation_id arriving on the subscribed channel are
#    routed by the gateway to a per-conversation hermes session.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["hermes", "gateway"]

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
#    `langchain-core` is pulled in because the `domyn` CLI eagerly imports the
#    langgraph integration (needed by step 4's `domyn install-plugin` call).
COPY wheels/ wheels/
RUN pip install --no-cache-dir wheels/domyn_agents-*.whl langchain-core

# 4) hermes-platform-gateway plugin.
#    `domyn install-plugin` drops the vendored plugin source plus its
#    `plugin.yaml` manifest directly into ${HERMES_HOME}/plugins/hermes_platform_gateway/,
#    which is what hermes' on-disk plugin scan picks up at startup. No pip
#    install or manual cp is needed — the plugin uses relative imports and
#    `domyn-agents` is already on sys.path from step 3.
RUN domyn install-plugin --agent-type hermes

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

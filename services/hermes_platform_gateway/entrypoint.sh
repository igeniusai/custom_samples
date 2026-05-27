#!/bin/sh
# hermes-platform-gateway entrypoint.
#
# hermes' gateway-mode config loader (gateway/run.py:_load_gateway_config →
# hermes_cli/config.read_raw_config) reads ~/.hermes/config.yaml RAW —
# without expanding ${VAR} references the way load_config() does. So we
# materialise the resolved config here before hermes starts.
#
# The image ships a template at /opt/hermes-config.template.yaml; we
# substitute env vars and write the result to $HERMES_HOME/config.yaml on
# every boot. Unconditional overwrite is intentional: this deployment
# treats hermes' config as ephemeral (Domyn is the source of truth for
# everything user-mutable).

set -e

: "${HERMES_HOME:=/root/.hermes}"
TEMPLATE=/opt/hermes-config.template.yaml
TARGET="$HERMES_HOME/config.yaml"

mkdir -p "$HERMES_HOME"

# Re-sync the platform-gateway plugin from the image into $HERMES_HOME on
# every boot. $HERMES_HOME is a docker-compose named volume that persists
# across rebuilds, so plugin files copied there at image-build time get
# shadowed by whatever the volume captured on its first run. Without this
# step, `docker compose build` updates the image but the running plugin
# stays stale until you `down -v`.
PLUGIN_SRC=/opt/hermes-platform-gateway/hermes_platform_gateway
PLUGIN_MANIFEST=/opt/hermes-platform-gateway/plugin.yaml
PLUGIN_DEST="$HERMES_HOME/plugins/hermes_platform_gateway"
mkdir -p "$PLUGIN_DEST"
cp -f "$PLUGIN_SRC"/*.py "$PLUGIN_MANIFEST" "$PLUGIN_DEST/"

python3 - <<'PY'
import os
import re
import sys

template_path = "/opt/hermes-config.template.yaml"
target_path = os.path.join(os.environ.get("HERMES_HOME", "/root/.hermes"), "config.yaml")

with open(template_path, encoding="utf-8") as f:
    text = f.read()

def _sub(match):
    name = match.group(1)
    val = os.environ.get(name)
    if val is None:
        print(f"warning: ${{{name}}} is not set in the environment", file=sys.stderr)
        return match.group(0)
    return val

resolved = re.sub(r"\$\{([A-Z0-9_]+)\}", _sub, text)

with open(target_path, "w", encoding="utf-8") as f:
    f.write(resolved)
PY

exec "$@"

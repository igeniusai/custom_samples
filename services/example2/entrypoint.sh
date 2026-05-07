#!/bin/sh
# Entrypoint for mcpesg.
#
# EXPOSE_SERVEO=true  → starts the uvicorn server AND opens a serveo.net tunnel
# EXPOSE_SERVEO=false → starts the uvicorn server only (default)

set -e

start_server() {
    echo "[entrypoint] Starting mcpesg server..."
    python -m mcpesg.main &
    SERVER_PID=$!
    echo "[entrypoint] Server PID: $SERVER_PID"
}

start_tunnel() {
    if [ "${SERVEO_RANDOM_SUBDOMAIN:-false}" = "true" ]; then
        TUNNEL_REMOTE="80:localhost:8080"
        echo "[entrypoint] Opening serveo.net tunnel (random subdomain → localhost:8080)..."
    else
        SERVEO_SUBDOMAIN="${SERVEO_SUBDOMAIN:-mcp}"
        TUNNEL_REMOTE="${SERVEO_SUBDOMAIN}:80:localhost:8080"
        echo "[entrypoint] Opening serveo.net tunnel (${SERVEO_SUBDOMAIN}:80 → localhost:8080)..."
    fi

    # Build ssh command: use identity file only if serveo_key is present
    SSH_IDENTITY=""
    if [ -f "/app/serveo_key" ]; then
        SSH_IDENTITY="-i /app/serveo_key"
    else
        echo "[entrypoint] No serveo_key found, connecting without identity file (public-key auth via ssh-agent or anonymous)..."
    fi

    # shellcheck disable=SC2086
    ssh $SSH_IDENTITY \
        -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=3 \
        -R $TUNNEL_REMOTE \
        serveo.net &
    TUNNEL_PID=$!
    echo "[entrypoint] Tunnel PID: $TUNNEL_PID"
}

# Trap SIGTERM/SIGINT and forward to child processes
shutdown() {
    echo "[entrypoint] Shutting down..."
    [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
    wait
    exit 0
}
trap shutdown TERM INT

start_server

if [ "${EXPOSE_SERVEO:-false}" = "true" ]; then
    start_tunnel
fi

# Wait for all background processes
wait

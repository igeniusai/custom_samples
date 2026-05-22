FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install domyn-agents from the bundled wheel (no private index required)
COPY wheels/ wheels/
RUN pip install --no-cache-dir wheels/domyn_agents-*.whl

# Copy the agent
COPY agent_expose.py .

# Connect to the Domyn platform via WebSocket relay
# All required values come from environment variables (see .env.example)
CMD ["sh", "-c", \
    "domyn expose agent_expose:agent \
        --channel-id $DOMYN_CHANNEL_ID \
        --space-id   $DOMYN_SPACE_ID \
        --base-url   $DOMYN_BASE_URL"]

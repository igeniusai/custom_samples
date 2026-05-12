FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install domyn-agents from the bundled wheel (no private index required)
COPY wheels/ wheels/
RUN pip install --no-cache-dir wheels/domyn_agents-*.whl \
    "langgraph>=0.2.0" \
    "langchain-core>=0.3.0"

# Copy the graph
COPY loan_assessment_graph.py .

# Connect to the Domyn platform via WebSocket relay
# All required values come from environment variables (see .env.example)
CMD ["sh", "-c", \
    "domyn expose loan_assessment_graph:graph \
        --channel-id $CHANNEL_ID \
        --space-id   $SPACE_ID \
        --base-url   $PLATFORM_BASE_URL"]

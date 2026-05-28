FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install domyn-agents from the bundled wheel (no private index required)
COPY wheels/ wheels/
RUN pip install --no-cache-dir wheels/domyn_agents-*.whl \
    "langgraph>=0.2.0" \
    "langchain>=0.3.0" \
    "langchain-core>=0.3.0" \
    "langchain-openai>=0.3.0"

# Copy the graph
COPY agent_expose.py .

# Connect to the Domyn platform via WebSocket relay
# All required values come from environment variables (see .env.example)
CMD ["domyn", "expose", "agent_expose:graph", "--framework", "langgraph"]

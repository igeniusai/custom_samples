FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /srv

# Install domyn-agents from the bundled wheel (copy the .whl from langgraph_agent_example/wheels/)
COPY langgraph_agent_controller/wheels/ wheels/
RUN if ls wheels/domyn_agents-*.whl 1>/dev/null 2>&1; then \
        pip install --no-cache-dir wheels/domyn_agents-*.whl \
            "langgraph>=0.2.0" \
            "langchain>=0.3.0" \
            "langchain-core>=0.3.0" \
            "langchain-openai>=0.3.0"; \
    fi

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic

COPY langgraph_agent_controller/main.py .
COPY langgraph_agent_controller/app/ app/
COPY langgraph_agent_example/ agent/

# The agent module lives at /srv/agent; app/process.py runs `domyn expose` with this cwd,
# and the loader only adds cwd to sys.path. Without it the import of agent_expose fails.
ENV AGENT_WORKDIR=/srv/agent

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

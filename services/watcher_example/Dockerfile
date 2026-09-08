FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY watcher_example.py .
COPY app/ app/
COPY templates/ templates/
RUN uv sync --frozen
EXPOSE 8089
CMD ["uv", "run", "uvicorn", "watcher_example:app", "--host", "0.0.0.0", "--port", "8089"]

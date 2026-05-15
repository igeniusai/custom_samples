FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /srv

# Install dependencies (cached layer — only re-runs when pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy application code
COPY guardrail_custom_ui_blueprint.py .
COPY app/ app/
COPY templates/ templates/

# Install the project itself (registers the `serve` console script)
RUN uv sync --frozen

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "guardrail_custom_ui_blueprint:app", "--host", "0.0.0.0", "--port", "8080"]

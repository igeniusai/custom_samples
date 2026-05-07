FROM ghcr.io/astral-sh/uv:0.10-python3.12-trixie-slim

# openssh-client is needed for the serveo.net tunnel
# chromium + deps are needed by kaleido (Plotly static image export)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    chromium \
    chromium-driver \
    libnss3 \
    libfreetype6 \
    libharfbuzz0b \
    ca-certificates \
    fonts-freefont-ttf \
    fonts-noto \
    libstdc++6 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxkbcommon0 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV KALEIDO_CHROME_BINARY=/usr/bin/chromium

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source code
COPY src/ ./src/
RUN mkdir -p /app/statics

# Install the project itself
RUN uv sync --frozen --no-dev

# Activate the venv for all subsequent RUN/CMD/ENTRYPOINT instructions
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy entrypoint and SSH key
COPY entrypoint.sh ./entrypoint.sh
COPY --chown=root:root . .
RUN chmod +x /app/entrypoint.sh && ([ -f /app/serveo_key ] && chmod 600 /app/serveo_key || true)

# false = server only | true = server + serveo tunnel
ENV EXPOSE_SERVEO=false

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]

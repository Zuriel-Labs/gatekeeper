# Gatekeeper - Policy Gateway for Google Workspace APIs
# Multi-arch build for amd64 + arm64 (RPi compatible)
# Uses uv for fast Python dependency installation
# Pass BUILD_VERSION from CI (e.g. docker/metadata-action) for versioned releases

ARG BUILD_VERSION=0.0.0

# ==================== Build Stage ====================
FROM python:3.15-slim AS builder

ARG BUILD_VERSION

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Copy project files
COPY pyproject.toml README.md ./
COPY gatekeeper/ gatekeeper/

# Inject version via pyproject.toml override (hatch-vcs can't see .git in Docker)
COPY scripts/ scripts/
RUN BUILD_VERSION="${BUILD_VERSION}" python3 scripts/set_version.py pyproject.toml && rm -rf scripts/

# Install the package and its dependencies
RUN uv pip install --system --no-cache .

# ==================== Runtime Stage ====================
FROM python:3.15-slim AS runtime

LABEL org.opencontainers.image.title="Gatekeeper"
LABEL org.opencontainers.image.description="Policy gateway for Google Workspace APIs with MCP server integration"
LABEL org.opencontainers.image.source="https://github.com/brimdor/gatekeeper"
LABEL org.opencontainers.image.vendor="Brimdor"
LABEL org.opencontainers.image.license="MIT"

# Install runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.15/site-packages/ /usr/local/lib/python3.15/site-packages/
COPY --from=builder /usr/local/bin/gatekeeper /usr/local/bin/gatekeeper

# Copy the application code
COPY gatekeeper/ /app/gatekeeper/

WORKDIR /app

# Create persistent data directory
RUN mkdir -p /data

# Environment defaults (secrets should be set via .env or env vars, not here)
ENV GATEKEEPER_HOST=0.0.0.0
ENV GATEKEEPER_PORT=8080
ENV GATEKEEPER_DATABASE_URL=sqlite+aiosqlite:////data/gatekeeper.db
ENV GATEKEEPER_GOOGLE_TOKEN_FILE=/data/google_token.json
ENV GATEKEEPER_DRIVE_ENABLED=false
ENV GATEKEEPER_GMAIL_ENABLED=false
ENV GATEKEEPER_CALENDAR_ENABLED=false
ENV GATEKEEPER_MCP_ENABLED=true

# Expose HTTP port (admin + API) and MCP SSE port
EXPOSE 8080

# Persistent volume for database, tokens, and secrets
VOLUME ["/data"]

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Entry point
CMD ["gatekeeper", "serve"]
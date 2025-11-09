# First, build the application in the `/app` directory.
# See `Dockerfile` for details.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter
# across both images. If using a managed Python version, it needs to be
# copied from the build image into the final image; see `standalone.Dockerfile`
# for an example.
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app
RUN apt-get update \
  && apt-get install -y libpq-dev gcc \
  && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-install-project --no-dev
ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm
# It is important to use the image that matches the builder, as the path to the
# Python executable must be the same, e.g., using `python:3.11-slim-bookworm`
# will fail.

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH"

ARG TARGETPLATFORM
ARG BUILDPLATFORM
ARG VERSION=0.0.1
LABEL org.opencontainers.image.title="postgres-mcp"
LABEL org.opencontainers.image.description="PostgreSQL Tuning and Analysis Tool - MCP Server (${TARGETPLATFORM})"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.source="https://github.com/crystaldba/postgres-mcp"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Andrey Shlyapin <andrey@skzd.ru>"
LABEL org.opencontainers.image.documentation="https://github.com/crystaldba/postgres-mcp"

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
  libpq-dev \
  iputils-ping \
  dnsutils \
  net-tools \
  && rm -rf /var/lib/apt/lists/*

COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

# Create directory for config.json (can be mounted as volume)
WORKDIR /app

# Expose the HTTP port for MCP server
EXPOSE 8000

# Run the postgres-mcp server
# Users can pass a database URI or individual connection arguments:
#   docker run -it --rm postgres-mcp postgres://user:pass@host:port/dbname
#   docker run -it --rm postgres-mcp -h myhost -p 5432 -U myuser -d mydb
# Or use config.json file (mounted as volume or copied into image)
ENTRYPOINT ["/app/docker-entrypoint.sh", "postgres-mcp"]
CMD []

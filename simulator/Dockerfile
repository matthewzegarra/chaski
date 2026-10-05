# syntax=docker/dockerfile:1.7
# "tools" image: Alembic migrations + the simulator. Build context: repository root.

# ---------- build
FROM python:3.14-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY libs/chaski_common/pyproject.toml libs/chaski_common/
COPY services/cuentas-api/pyproject.toml services/cuentas-api/
COPY services/core-api/pyproject.toml services/core-api/
COPY services/ia-api/pyproject.toml services/ia-api/
COPY simulator/pyproject.toml simulator/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package chaski-simulator --no-install-workspace
COPY libs/chaski_common libs/chaski_common
COPY simulator simulator
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package chaski-simulator --no-editable

# ---------- runtime (one-off jobs: migrate, seed, live)
FROM python:3.14-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="chaski-tools" \
      org.opencontainers.image.description="Interbank CHASKI - migraciones y simulador"
RUN useradd --system --uid 10001 --no-create-home chaski
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY db ./db
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001
CMD ["alembic", "-c", "db/alembic.ini", "upgrade", "head"]

# syntax=docker/dockerfile:1.7
# cuentas-api (the service with full CI/CD). Build context: repository root (the uv workspace).

# ---------- build: resolve the locked dependencies into /opt/venv
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
    uv sync --frozen --no-dev --package cuentas-api --no-install-workspace
COPY libs/chaski_common libs/chaski_common
COPY services/cuentas-api services/cuentas-api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package cuentas-api --no-editable

# ---------- runtime: slim and non-root
FROM python:3.14-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="chaski-cuentas-api" \
      org.opencontainers.image.description="Interbank CHASKI - cuentas-api"
RUN useradd --system --uid 10001 --no-create-home chaski
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_NAME=cuentas-api
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "cuentas_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]

# syntax=docker/dockerfile:1.7
# core-api. Build context: repository root (the uv workspace).

# ---------- build: resolve the locked dependencies into /opt/venv
FROM python:3.15-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends unixodbc-dev g++ \
    && rm -rf /var/lib/apt/lists/*
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
    uv sync --frozen --no-dev --package core-api --no-install-workspace
COPY libs/chaski_common libs/chaski_common
COPY services/core-api services/core-api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package core-api --no-editable

# ---------- runtime: slim, non-root, ODBC 18 for Azure SQL
FROM python:3.15-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="chaski-core-api" \
      org.opencontainers.image.description="Interbank CHASKI - core-api"
# Microsoft ODBC Driver 18: gold lives in Azure SQL in the cloud (ANALYTICS_DIALECT=tsql).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && apt-get purge -y curl gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --no-create-home chaski \
    && mkdir -p /data/uploads && chown chaski:chaski /data/uploads
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_NAME=core-api UPLOADS_DIR=/data/uploads
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "core_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]

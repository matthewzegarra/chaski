"""FastAPI application factory shared by every CHASKI service."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from chaski_common.db import ping
from chaski_common.logging import configure_logging, correlation_id_var, get_logger
from chaski_common.middleware import (
    CorrelationIdMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from chaski_common.settings import get_common_settings
from chaski_common.telemetry import configure_telemetry

API_PREFIX = "/api/v1"

log = get_logger(__name__)


def create_app(
    *,
    title: str,
    description: str,
    routers: Sequence[APIRouter] = (),
    readiness_check: Callable[[], bool] = ping,
) -> FastAPI:
    settings = get_common_settings()
    configure_logging(settings.service_name, settings.log_level)

    app = FastAPI(title=title, description=description, version=settings.service_version)

    # Starlette runs the last-added middleware first, so CorrelationId wraps everything.
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Correlation-ID",
            "X-Chaski-Signature",
        ],
        expose_headers=["X-Correlation-ID"],
    )
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.service_name,
            "version": settings.service_version,
        }

    @app.get("/ready", tags=["health"])
    def ready() -> JSONResponse:
        ok = readiness_check()
        return JSONResponse(
            {"status": "ready" if ok else "not_ready", "service": settings.service_name},
            status_code=200 if ok else 503,
        )

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(
            {"detail": "Error interno", "correlation_id": correlation_id_var.get()},
            status_code=500,
        )

    for router in routers:
        app.include_router(router, prefix=API_PREFIX)

    configure_telemetry(app, settings)
    return app

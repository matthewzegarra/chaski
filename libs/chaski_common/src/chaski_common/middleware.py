"""HTTP middleware: correlation id + access log, security headers and in-memory rate limiting."""

from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from chaski_common.logging import correlation_id_var, get_logger

log = get_logger("chaski.access")
_CID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_UNMETERED = ("/health", "/ready")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-correlation-id", "")
        cid = incoming if _CID_RE.match(incoming) else str(uuid.uuid4())
        token = correlation_id_var.set(cid)
        structlog.contextvars.bind_contextvars(correlation_id=cid)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Correlation-ID"] = cid
            return response
        finally:
            if request.url.path not in _UNMETERED:
                log.info(
                    "http_request",
                    method=request.method,
                    path=request.url.path,
                    status=status_code,
                    duration_ms=round((time.perf_counter() - start) * 1000, 1),
                )
            structlog.contextvars.unbind_contextvars("correlation_id")
            correlation_id_var.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith(("/docs", "/redoc")):
            h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            h.setdefault("Cache-Control", "no-store")
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed one-minute window per client IP. Good enough for a single replica (see D15)."""

    def __init__(self, app: Any, per_minute: int) -> None:
        super().__init__(app)
        self.per_minute = per_minute
        self._window = 0
        self._counts: defaultdict[str, int] = defaultdict(int)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self.per_minute <= 0 or request.url.path in _UNMETERED or request.method == "OPTIONS":
            return await call_next(request)
        window = int(time.time() // 60)
        if window != self._window:
            self._window = window
            self._counts.clear()
        fwd = request.headers.get("x-forwarded-for")
        ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")
        self._counts[ip] += 1
        if self._counts[ip] > self.per_minute:
            return JSONResponse(
                {"detail": "Demasiadas solicitudes, intenta en un minuto"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        return await call_next(request)

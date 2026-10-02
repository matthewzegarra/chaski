"""OpenTelemetry -> Application Insights. Disabled unless the connection string is set."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from chaski_common.settings import CommonSettings

_configured = False


def configure_telemetry(app: FastAPI, settings: CommonSettings) -> bool:
    global _configured
    conn = settings.applicationinsights_connection_string
    if not conn:
        return False
    if not _configured:
        os.environ.setdefault("OTEL_SERVICE_NAME", settings.service_name)
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        configure_azure_monitor(connection_string=conn, logger_name="chaski")
        HTTPXClientInstrumentor().instrument()
        _configured = True

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready")
    return True

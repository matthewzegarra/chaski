"""OpenTelemetry -> Application Insights. Disabled unless the connection string is set.

Traces: FastAPI (health/ready excluded), outgoing httpx calls and SQLAlchemy queries.
Logs: every record of the root logger, after `RedactingFilter` has removed PII, so the
exporter never ships DNIs, emails, phones or card numbers.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from chaski_common.logging import RedactingFilter

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
        os.environ.setdefault(
            "OTEL_RESOURCE_ATTRIBUTES", f"deployment.environment={settings.chaski_env}"
        )
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from chaski_common.db import get_engine

        root = logging.getLogger()
        before = set(root.handlers)
        configure_azure_monitor(connection_string=conn, logger_name="")
        for handler in root.handlers:
            if handler not in before:
                handler.addFilter(RedactingFilter())
        HTTPXClientInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument(engine=get_engine())
        _configured = True

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready")
    return True

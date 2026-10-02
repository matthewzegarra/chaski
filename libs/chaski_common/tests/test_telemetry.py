from __future__ import annotations

import logging

from chaski_common.logging import RedactingFilter
from chaski_common.settings import CommonSettings
from chaski_common.telemetry import configure_telemetry
from fastapi import FastAPI


def _record(msg: object, *args: object) -> logging.LogRecord:
    return logging.LogRecord("lib", logging.INFO, __file__, 1, msg, args or None, None)


def test_filter_redacts_third_party_messages_and_args() -> None:
    rec = _record("cliente %s con tarjeta %s", "45678912", "4111111111111111")
    assert RedactingFilter().filter(rec)
    assert rec.getMessage() == "cliente [REDACTED_DNI] con tarjeta [REDACTED_PAN]"


def test_filter_redacts_structured_events() -> None:
    rec = _record({"event": "x", "email": "rosa@gmail.com"})
    RedactingFilter().filter(rec)
    assert rec.msg == {"event": "x", "email": "[REDACTED_EMAIL]"}


def test_filter_redacts_exception_text() -> None:
    rec = _record("boom")
    rec.exc_text = "ValueError: DNI 45678912 inválido"
    RedactingFilter().filter(rec)
    assert "45678912" not in rec.exc_text


def test_telemetry_is_off_without_connection_string() -> None:
    settings = CommonSettings(dev_jwt_secret="x" * 40, applicationinsights_connection_string=None)  # type: ignore[arg-type]
    assert configure_telemetry(FastAPI(), settings) is False


def test_stdout_handler_has_the_filter() -> None:
    from chaski_common.logging import configure_logging

    configure_logging("test", "INFO")
    assert any(
        isinstance(f, RedactingFilter) for h in logging.getLogger().handlers for f in h.filters
    )

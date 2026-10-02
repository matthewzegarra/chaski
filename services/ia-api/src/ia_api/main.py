"""Chaski ia-api: ASGI entrypoint."""

from chaski_common.app import create_app

from ia_api.routers import cases, insights

app = create_app(
    title="Chaski ia-api",
    description="Clasificador de quejas, scoring, asistente, resumen ejecutivo, NL2SQL y KYC.",
    routers=[cases.router, insights.router],
)

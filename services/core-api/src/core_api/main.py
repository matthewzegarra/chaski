"""Chaski core-api: ASGI entrypoint."""

from chaski_common.app import create_app

app = create_app(
    title="Chaski core-api",
    description="Clientes, onboarding, tarjetas, préstamos, quejas, fraude, consola y analítica.",
)

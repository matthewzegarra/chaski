"""Chaski core-api: ASGI entrypoint."""

from chaski_common.app import create_app

from core_api.routers import (
    analytics,
    cards,
    complaints,
    customers,
    demo,
    dev,
    devops,
    fraud,
    loans,
    onboarding,
    ops,
    security,
)

app = create_app(
    title="Chaski core-api",
    description="Clientes, onboarding, tarjetas, préstamos, quejas, fraude, consola y analítica.",
    routers=[
        dev.router,
        customers.router,
        onboarding.router,
        cards.router,
        loans.router,
        complaints.router,
        fraud.router,
        ops.router,
        analytics.router,
        security.router,
        devops.router,
        demo.router,
    ],
)

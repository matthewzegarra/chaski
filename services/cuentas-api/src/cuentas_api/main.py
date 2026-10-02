"""Chaski cuentas-api: ASGI entrypoint."""

from chaski_common.app import create_app

from cuentas_api.routers import accounts, payments

app = create_app(
    title="Chaski cuentas-api",
    description="Saldo, movimientos, transferencias y pagos con tarjeta.",
    routers=[accounts.router, payments.router],
)

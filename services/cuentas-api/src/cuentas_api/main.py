"""Chaski cuentas-api: ASGI entrypoint."""

from chaski_common.app import create_app

app = create_app(
    title="Chaski cuentas-api",
    description="Saldo, movimientos, transferencias y pagos con tarjeta.",
)

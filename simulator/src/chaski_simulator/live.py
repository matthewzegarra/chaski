"""--live mode: keeps generating transactions through cuentas-api every few seconds.

Going through the API (instead of writing to the database) means each transaction is
evaluated by the fraud rules engine and published to Eventstream, like real traffic.
Requires AUTH_MODE=dev: tokens are requested from core-api's /dev/token endpoint.
"""

from __future__ import annotations

import random
import time
import uuid
from typing import Any

import httpx
import psycopg

from chaski_simulator import catalog as cat
from chaski_simulator.loader import to_psycopg_url

_PICK_SQL = """
SELECT c.id, c.first_name, c.region, a.id, a.balance, k.id
FROM core.customers c
JOIN core.accounts a ON a.customer_id = c.id AND a.currency = 'PEN' AND a.status = 'ACTIVA'
LEFT JOIN core.cards k ON k.account_id = a.id AND k.status = 'ACTIVA'
WHERE c.kyc_status = 'APROBADO' AND a.balance > 200
ORDER BY random()
LIMIT 50
"""


def _token(client: httpx.Client, core_url: str, customer_id: uuid.UUID, name: str) -> str:
    resp = client.post(
        f"{core_url}/api/v1/dev/token",
        json={
            "sub": f"cliente-{customer_id}",
            "name": name,
            "roles": ["Cliente"],
            "customer_id": str(customer_id),
        },
    )
    resp.raise_for_status()
    return str(resp.json()["access_token"])


def run_live(
    db_url: str, cuentas_url: str, core_url: str, interval: float, seed: int | None
) -> None:
    rng = random.Random(seed)
    with psycopg.connect(to_psycopg_url(db_url)) as conn:
        pool: list[tuple[Any, ...]] = conn.execute(_PICK_SQL).fetchall()
        numbers = [
            r[0]
            for r in conn.execute("SELECT number FROM core.accounts WHERE currency='PEN' LIMIT 500")
        ]
    if not pool:
        raise SystemExit("No customers with balance found. Run the seed first.")
    tokens: dict[uuid.UUID, str] = {}
    print(f"Live mode: {len(pool)} customers, one transaction every ~{interval}s. Ctrl+C to stop.")
    with httpx.Client(timeout=10) as client:
        while True:
            cid, name, region, account_id, _balance, card_id = rng.choice(pool)
            if cid not in tokens:
                tokens[cid] = _token(client, core_url, cid, name)
            headers = {
                "Authorization": f"Bearer {tokens[cid]}",
                "Idempotency-Key": str(uuid.uuid4()),
            }
            if card_id and rng.random() < 0.6:
                body: dict[str, Any] = {
                    "card_id": str(card_id),
                    "amount": round(rng.lognormvariate(3.6, 0.7), 2),
                    "merchant": rng.choice(cat.MERCHANTS_POS),
                    "city": cat.REGION_BY_NAME[region].cities[0],
                    "channel": "POS",
                }
                resp = client.post(
                    f"{cuentas_url}/api/v1/card-payments", json=body, headers=headers
                )
            else:
                body = {
                    "from_account_id": str(account_id),
                    "to_account_number": rng.choice(numbers),
                    "amount": round(rng.lognormvariate(4.2, 0.8), 2),
                    "description": "Transferencia simulada",
                }
                resp = client.post(f"{cuentas_url}/api/v1/transfers", json=body, headers=headers)
            print(f"{time.strftime('%H:%M:%S')} {resp.request.url.path} -> {resp.status_code}")
            time.sleep(max(0.2, rng.uniform(interval * 0.5, interval * 1.5)))

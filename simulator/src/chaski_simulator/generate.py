"""Deterministic synthetic data for the core and ops schemas.

Everything is driven by one `random.Random(seed)`; dates are relative to `now`, so the
same seed always yields the same structure (counts, distributions, relationships).
"""

from __future__ import annotations

import math
import random
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from chaski_common.business_days import regulatory_deadline
from faker import Faker

from chaski_simulator import catalog as cat

WINDOW_DAYS = 182
N_CUSTOMERS = 1000
N_LOANS = 400
N_COMPLAINTS = 150
USD_PEN = Decimal("3.75")


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def monthly_rate(tea: float) -> float:
    return float((1 + tea) ** (1 / 12) - 1)


def french_payment(principal: float, tea: float, months: int) -> float:
    i = monthly_rate(tea)
    return principal * i / (1 - (1 + i) ** -months)


def balance_after(principal: float, tea: float, months: int, paid: int) -> float:
    """Outstanding principal after `paid` instalments of a French amortisation."""
    if paid >= months:
        return 0.0
    i = monthly_rate(tea)
    c = french_payment(principal, tea, months)
    return max(0.0, principal * (1 + i) ** paid - c * ((1 + i) ** paid - 1) / i)


def months_between(start: datetime, end: datetime) -> int:
    return max(0, (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day))


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


@dataclass
class Dataset:
    now: datetime
    customers: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)
    loans: list[dict[str, Any]] = field(default_factory=list)
    installments: list[dict[str, Any]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    complaints: list[dict[str, Any]] = field(default_factory=list)
    kyc_documents: list[dict[str, Any]] = field(default_factory=list)
    fraud_alerts: list[dict[str, Any]] = field(default_factory=list)
    pipeline_runs: list[dict[str, Any]] = field(default_factory=list)
    quality_checks: list[dict[str, Any]] = field(default_factory=list)
    quarantine: list[dict[str, Any]] = field(default_factory=list)
    ai_interactions: list[dict[str, Any]] = field(default_factory=list)
    # Per-loan final days past due, used by gold to draw the delinquency trajectory.
    loan_final_dpd: dict[uuid.UUID, int] = field(default_factory=dict)
    card_utilisation: dict[uuid.UUID, float] = field(default_factory=dict)


class Generator:
    def __init__(self, seed: int = 42, now: datetime | None = None) -> None:
        self.rng = random.Random(seed)
        self.fake = Faker("es_ES")
        self.fake.seed_instance(seed)
        self.now = (now or datetime.now(UTC)).replace(microsecond=0)
        self.start = self.now - timedelta(days=WINDOW_DAYS)
        self.ds = Dataset(now=self.now)
        self._dnis: set[str] = set()
        self._emails: set[str] = set()
        self._account_numbers: set[str] = set()

    # ------------------------------------------------------------ helpers
    def new_id(self) -> uuid.UUID:
        return uuid.UUID(int=self.rng.getrandbits(128), version=4)

    def choice_weighted(
        self, pairs: tuple[tuple[str, float], ...] | list[tuple[str, float]]
    ) -> str:
        names, weights = zip(*pairs, strict=True)
        return self.rng.choices(names, weights=weights, k=1)[0]

    def rand_dt(self, start: datetime, end: datetime) -> datetime:
        if end <= start:
            return start
        seconds = int((end - start).total_seconds())
        moment = start + timedelta(seconds=self.rng.randint(0, seconds))
        # Bias towards business hours (07:00-22:00 local ≈ 12:00-03:00 UTC).
        hour = self.rng.choices(range(24), weights=_HOUR_WEIGHTS, k=1)[0]
        candidate = datetime.combine(moment.date(), time(hour, self.rng.randint(0, 59)), UTC)
        return candidate if start <= candidate <= end else moment

    def dni(self) -> str:
        while True:
            value = str(self.rng.randint(10_000_000, 79_999_999))
            if value not in self._dnis:
                self._dnis.add(value)
                return value

    def account_number(self, product: str) -> str:
        prefix = "200" if product == "AHORRO_SOLES" else "210"
        while True:
            value = f"{prefix}-{self.rng.randint(3_000_000_000, 3_999_999_999)}"
            if value not in self._account_numbers:
                self._account_numbers.add(value)
                return value

    # ------------------------------------------------------------ entities
    def run(self) -> Dataset:
        self.make_customers()
        self.make_accounts_and_cards()
        self.make_loans()
        self.make_transactions()
        self.make_fraud_alerts()
        self.make_complaints()
        self.make_kyc_documents()
        self.make_pipeline_history()
        return self.ds

    def make_customers(self) -> None:
        regions = [(r.name, r.weight) for r in cat.REGIONS]
        for n in range(N_CUSTOMERS):
            first = (
                self.rng.choice(cat.PERUVIAN_FIRST_NAMES)
                if self.rng.random() < 0.5
                else self.fake.first_name()
            )
            last = " ".join(
                self.rng.choice(cat.PERUVIAN_SURNAMES)
                if self.rng.random() < 0.65
                else self.fake.last_name()
                for _ in range(2)
            )
            local = f"{_ascii(first.split()[0])}.{_ascii(last.split()[0])}{n}"
            email = f"{local}@{self.rng.choice(cat.EMAIL_DOMAINS)}"
            segment = self.choice_weighted(cat.SEGMENTS)
            kyc = self.choice_weighted(
                (("APROBADO", 0.955), ("PENDIENTE", 0.035), ("RECHAZADO", 0.01))
            )
            if kyc == "PENDIENTE":
                created = self.rand_dt(self.now - timedelta(days=10), self.now)
            elif n < 4:  # a few new customers today for the "clientes nuevos hoy" KPI
                created = self.rand_dt(self.now.replace(hour=0, minute=0, second=0), self.now)
            elif self.rng.random() < 0.2:
                created = self.rand_dt(self.start, self.now - timedelta(days=1))
            else:
                created = self.rand_dt(self.now - timedelta(days=3 * 365), self.start)
            income_range = {
                "MASIVO": (1200, 4500),
                "PREFERENTE": (6000, 20000),
                "PYME": (4000, 15000),
            }
            lo, hi = income_range[segment]
            age = self.rng.randint(18, 75)
            self.ds.customers.append(
                {
                    "id": self.new_id(),
                    "document_type": "DNI",
                    "document_number": self.dni(),
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "phone": "9" + "".join(str(self.rng.randint(0, 9)) for _ in range(8)),
                    "birth_date": (
                        self.now - timedelta(days=age * 365 + self.rng.randint(0, 364))
                    ).date(),
                    "segment": segment,
                    "region": self.choice_weighted(regions),
                    "kyc_status": kyc,
                    "risk_level": self.choice_weighted(
                        (("BAJO", 0.7), ("MEDIO", 0.24), ("ALTO", 0.06))
                    ),
                    "monthly_income": money(self.rng.uniform(lo, hi)),
                    "kyc_decided_by": None if kyc == "PENDIENTE" else "atencion.demo",
                    "kyc_decided_at": None
                    if kyc == "PENDIENTE"
                    else created + timedelta(hours=self.rng.randint(1, 30)),
                    "created_at": created,
                }
            )

    def make_accounts_and_cards(self) -> None:
        for c in self.ds.customers:
            if c["kyc_status"] != "APROBADO":
                continue
            opened = c["created_at"] + timedelta(hours=self.rng.randint(1, 48))
            opened = min(opened, self.now)
            soles = self._account(c, "AHORRO_SOLES", "PEN", opened)
            dollar_p = {"MASIVO": 0.28, "PREFERENTE": 0.6, "PYME": 0.45}[c["segment"]]
            if self.rng.random() < dollar_p:
                self._account(
                    c, "AHORRO_DOLARES", "USD", opened + timedelta(days=self.rng.randint(0, 60))
                )
            if self.rng.random() < 0.70:
                self._card(c, soles["id"], "DEBITO", opened)
            if self.rng.random() < 0.25:
                self._card(c, None, "CREDITO", opened + timedelta(days=self.rng.randint(5, 90)))

    def _account(
        self, c: dict[str, Any], product: str, currency: str, opened: datetime
    ) -> dict[str, Any]:
        acc = {
            "id": self.new_id(),
            "customer_id": c["id"],
            "number": self.account_number(product),
            "product": product,
            "currency": currency,
            "balance": Decimal("0"),
            "status": "ACTIVA",
            "opened_at": min(opened, self.now),
            "_segment": c["segment"],
            "_region": c["region"],
        }
        self.ds.accounts.append(acc)
        return acc

    def _card(
        self, c: dict[str, Any], account_id: uuid.UUID | None, kind: str, created: datetime
    ) -> None:
        brand = self.choice_weighted(
            (("VISA", 0.6), ("MASTERCARD", 0.35), ("AMEX", 0.05 if kind == "CREDITO" else 0.0))
        )
        limit = None
        if kind == "CREDITO":
            base = {"MASIVO": 3000, "PREFERENTE": 20000, "PYME": 12000}[c["segment"]]
            limit = money(round(base * self.rng.uniform(0.5, 2.0), -2))
        card_id = self.new_id()
        self.ds.cards.append(
            {
                "id": card_id,
                "customer_id": c["id"],
                "account_id": account_id,
                "type": kind,
                "token": f"tok_{self.rng.getrandbits(96):024x}",
                "last4": f"{self.rng.randint(0, 9999):04d}",
                "brand": brand,
                "credit_limit": limit,
                "status": "BLOQUEADA" if self.rng.random() < 0.03 else "ACTIVA",
                "created_at": min(created, self.now),
            }
        )
        if kind == "CREDITO":
            self.ds.card_utilisation[card_id] = self.rng.uniform(0.2, 0.7)

    def make_loans(self) -> None:
        approved = [c for c in self.ds.customers if c["kyc_status"] == "APROBADO"]
        for _ in range(N_LOANS):
            c = self.rng.choice(approved)
            status = self.choice_weighted(
                (
                    ("DESEMBOLSADO", 0.68),
                    ("CANCELADO", 0.07),
                    ("RECHAZADO", 0.09),
                    ("APROBADO", 0.04),
                    ("SOLICITADO", 0.12),
                )
            )
            lo, hi, tea_lo, tea_hi = {
                "MASIVO": (2000, 25000, 0.30, 0.45),
                "PREFERENTE": (10000, 80000, 0.15, 0.25),
                "PYME": (15000, 100000, 0.20, 0.35),
            }[c["segment"]]
            amount = round(self.rng.uniform(lo, hi) / 500) * 500
            term = self.rng.choice((12, 18, 24, 36, 48))
            tea = round(self.rng.uniform(tea_lo, tea_hi), 4)
            if status in ("SOLICITADO", "APROBADO"):
                created = self.rand_dt(self.now - timedelta(days=20), self.now)
            else:
                created = self.rand_dt(
                    max(c["created_at"], self.now - timedelta(days=540)),
                    self.now - timedelta(days=25),
                )
            loan: dict[str, Any] = {
                "id": self.new_id(),
                "customer_id": c["id"],
                "product": "CONSUMO",
                "amount": money(amount),
                "term_months": term,
                "rate_tea": Decimal(str(tea)),
                "status": status,
                "days_past_due": 0,
                "outstanding_balance": Decimal("0"),
                "ai_score": None,
                "ai_explanation": None,
                "decided_by": None if status == "SOLICITADO" else "riesgos.demo",
                "decided_at": None
                if status == "SOLICITADO"
                else created + timedelta(hours=self.rng.randint(2, 48)),
                "disbursed_at": None,
                "created_at": created,
                "_region": c["region"],
                "_segment": c["segment"],
            }
            if status in ("DESEMBOLSADO", "CANCELADO"):
                self._disburse(loan, c)
            self.ds.loans.append(loan)

    def _disburse(self, loan: dict[str, Any], c: dict[str, Any]) -> None:
        disbursed = loan["created_at"] + timedelta(days=self.rng.randint(1, 3))
        loan["disbursed_at"] = disbursed
        amount, tea, term = float(loan["amount"]), float(loan["rate_tea"]), loan["term_months"]
        payment = money(french_payment(amount, tea, term))
        elapsed = min(term, months_between(disbursed, self.now))
        dpd = 0
        if loan["status"] == "DESEMBOLSADO":
            p = (
                cat.REGION_BY_NAME[c["region"]].delinquency
                * cat.SEGMENT_DELINQUENCY_FACTOR[c["segment"]]
            )
            if self.rng.random() < p:
                bucket = self.choice_weighted(
                    (("CPP", 0.45), ("Deficiente", 0.25), ("Dudoso", 0.18), ("Pérdida", 0.12))
                )
                lo, hi = {
                    "CPP": (9, 30),
                    "Deficiente": (31, 60),
                    "Dudoso": (61, 120),
                    "Pérdida": (121, 240),
                }[bucket]
                dpd = self.rng.randint(lo, hi)
            elif self.rng.random() < 0.10:
                dpd = self.rng.randint(1, 8)
        unpaid = math.ceil(dpd / 30) if dpd else 0
        paid = max(0, elapsed - unpaid)
        if loan["status"] == "CANCELADO" or (elapsed >= term and dpd == 0):
            # Fully repaid (on schedule or prepaid): nothing outstanding.
            loan["status"] = "CANCELADO"
            paid, dpd = term, 0
            loan["outstanding_balance"] = Decimal("0")
        else:
            loan["outstanding_balance"] = money(balance_after(amount, tea, term, paid))
        loan["days_past_due"] = dpd
        self.ds.loan_final_dpd[loan["id"]] = dpd
        for k in range(1, term + 1):
            due = (disbursed + timedelta(days=30 * k)).date()
            self.ds.installments.append(
                {
                    "loan_id": loan["id"],
                    "number": k,
                    "due_date": due,
                    "amount": payment,
                    "paid_at": min(
                        datetime.combine(due, time(15), UTC)
                        - timedelta(days=self.rng.randint(0, 3)),
                        self.now,
                    )
                    if k <= paid
                    else None,
                }
            )

    # ------------------------------------------------------------ transactions
    def make_transactions(self) -> None:
        cards_by_account: dict[uuid.UUID, dict[str, Any]] = {
            c["account_id"]: c for c in self.ds.cards if c["account_id"] is not None
        }
        all_numbers = [a["number"] for a in self.ds.accounts if a["currency"] == "PEN"]
        for acc in self.ds.accounts:
            self._account_history(acc, cards_by_account.get(acc["id"]), all_numbers)

    def _account_history(
        self, acc: dict[str, Any], card: dict[str, Any] | None, numbers: list[str]
    ) -> None:
        rng = self.rng
        start = max(acc["opened_at"], self.start)
        if start >= self.now:
            start = self.now - timedelta(minutes=5)
        region = cat.REGION_BY_NAME[acc["_region"]]
        segment = acc["_segment"]
        usd = acc["currency"] == "USD"
        scale = {"MASIVO": 1.0, "PREFERENTE": 3.5, "PYME": 2.5}[segment] / (
            float(USD_PEN) if usd else 1.0
        )
        events: list[tuple[datetime, str, float, dict[str, Any]]] = []

        opening = float(scale) * rng.uniform(300, 3000)
        events.append(
            (start, "DEPOSITO", opening, {"channel": "WEB", "description": "Depósito inicial"})
        )

        # Payroll on the last business-ish day of the month, interest and maintenance fee.
        has_payroll = not usd and rng.random() < 0.7
        salary = float(scale) * rng.uniform(1100, 4000)
        month_cursor = date(start.year, start.month, 1)
        while month_cursor <= self.now.date():
            nxt = (month_cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            payday = datetime.combine(nxt - timedelta(days=2), time(14), UTC)
            month_end = datetime.combine(nxt - timedelta(days=1), time(23, 30), UTC)
            if has_payroll and start < payday <= self.now:
                events.append(
                    (
                        payday,
                        "DEPOSITO",
                        salary * rng.uniform(0.97, 1.03),
                        {"channel": "WEB", "description": "Abono de haberes"},
                    )
                )
            if start < month_end <= self.now:
                events.append(
                    (
                        month_end,
                        "INTERES",
                        -1.0,
                        {"channel": "WEB", "description": "Intereses ganados"},
                    )
                )
                if segment != "PREFERENTE" and rng.random() < 0.35:
                    events.append(
                        (
                            month_end,
                            "COMISION",
                            rng.choice((4.5, 6.0, 9.0)),
                            {"channel": "WEB", "description": "Mantenimiento de cuenta"},
                        )
                    )
            month_cursor = nxt

        lam = 18 if usd else {"MASIVO": 46, "PREFERENTE": 82, "PYME": 88}[segment]
        span = (self.now - start).total_seconds() / (WINDOW_DAYS * 86400)
        n = max(1, int(rng.gauss(lam * span, lam * span * 0.25)))
        for _ in range(n):
            when = self.rand_dt(start + timedelta(minutes=1), self.now)
            kind = rng.choices(
                (
                    "PAGO_TARJETA",
                    "PAGO_SERVICIO",
                    "RETIRO",
                    "TRANSFERENCIA_OUT",
                    "TRANSFERENCIA_IN",
                ),
                weights=(0.42 if card else 0.0, 0.16, 0.14, 0.16, 0.12),
            )[0]
            meta: dict[str, Any]
            if kind == "PAGO_TARJETA":
                online = rng.random() < 0.3
                city = (
                    region.cities[0] if rng.random() < 0.93 else rng.choice(cat.REGIONS).cities[0]
                )
                meta = {
                    "channel": "WEB" if online else "POS",
                    "card_id": card["id"] if card else None,
                    "merchant": rng.choice(cat.MERCHANTS_ONLINE if online else cat.MERCHANTS_POS),
                    "city": None if online else city,
                }
                amount = float(scale) * rng.lognormvariate(3.6, 0.8)
            elif kind == "PAGO_SERVICIO":
                meta = {"channel": rng.choice(("APP", "WEB")), "merchant": rng.choice(cat.SERVICES)}
                amount = float(scale) * rng.uniform(30, 250)
            elif kind == "RETIRO":
                meta = {"channel": "ATM", "city": rng.choice(region.cities)}
                amount = float(rng.choice((50, 100, 150, 200, 300, 400, 500))) / (
                    float(USD_PEN) if usd else 1
                )
            elif kind == "TRANSFERENCIA_OUT":
                meta = {
                    "channel": rng.choice(("APP", "APP", "WEB")),
                    "counterparty_account": rng.choice(numbers) if numbers else None,
                }
                amount = float(scale) * rng.lognormvariate(4.6, 0.9)
            else:
                meta = {
                    "channel": "APP",
                    "counterparty_account": rng.choice(numbers) if numbers else None,
                }
                amount = float(scale) * rng.lognormvariate(4.5, 0.9)
            events.append((when, kind, amount, meta))

        events.sort(key=lambda e: e[0])
        balance = 0.0
        credit_types = {"DEPOSITO", "TRANSFERENCIA_IN", "INTERES"}
        for when, kind, amount, meta in events:
            if kind == "INTERES":
                amount = balance * 0.005 / 12
                if amount < 0.01:
                    continue
            amount = float(money(amount))
            if amount <= 0:
                continue
            if kind in credit_types:
                balance += amount
            else:
                if amount > balance:
                    continue
                balance -= amount
            self.ds.transactions.append(
                {
                    "id": self.new_id(),
                    "account_id": acc["id"],
                    "card_id": meta.get("card_id"),
                    "type": kind,
                    "amount": money(amount),
                    "currency": acc["currency"],
                    "channel": meta["channel"],
                    "merchant": meta.get("merchant"),
                    "city": meta.get("city"),
                    "counterparty_account": meta.get("counterparty_account"),
                    "description": meta.get("description"),
                    "created_at": when,
                    "_customer_id": acc["customer_id"],
                }
            )
        acc["balance"] = money(balance)

    # ------------------------------------------------------------ ops data
    def make_fraud_alerts(self) -> None:
        rng = self.rng
        candidates = [
            t
            for t in self.ds.transactions
            if t["type"] in ("TRANSFERENCIA_OUT", "PAGO_TARJETA") and t["amount"] > 400
        ]
        picked = rng.sample(candidates, min(45, len(candidates)))
        rules = (
            ("R2_MONTO_ATIPICO", "Monto mayor a 3 veces el promedio de 30 días"),
            ("R3_CIUDAD_DISTINTA", "Pago en ciudad distinta en menos de 30 minutos"),
            ("R4_BENEFICIARIO_NUEVO", "Transferencia mayor a S/ 5,000 a beneficiario nuevo"),
            ("R1_VELOCIDAD", "Más de 5 transferencias en 2 minutos"),
        )
        for i, t in enumerate(sorted(picked, key=lambda x: x["created_at"])):
            rule, desc = rules[i % len(rules)]
            recent = t["created_at"] > self.now - timedelta(days=2)
            status = (
                "ABIERTA"
                if recent
                else rng.choice(("CONFIRMADA", "DESCARTADA", "DESCARTADA", "DESCARTADA"))
            )
            source = "FABRIC" if i % 9 == 0 else "RULES"
            self.ds.fraud_alerts.append(
                {
                    "id": self.new_id(),
                    "transaction_id": t["id"],
                    "customer_id": t["_customer_id"],
                    "rule": "FABRIC_ANOMALIA" if source == "FABRIC" else rule,
                    "score": Decimal(str(round(rng.uniform(55, 98), 2))),
                    "source": source,
                    "status": status,
                    "details": {
                        "descripcion": "Anomalía detectada por modelo en Fabric"
                        if source == "FABRIC"
                        else desc
                    },
                    "resolved_by": None if status == "ABIERTA" else "fraude.demo",
                    "resolved_at": None
                    if status == "ABIERTA"
                    else t["created_at"] + timedelta(hours=rng.randint(1, 20)),
                    "created_at": t["created_at"] + timedelta(seconds=2),
                }
            )
        # Make sure the Chaski Guard screen has open alerts during the demo.
        for t in sorted(candidates, key=lambda x: x["created_at"])[-5:]:
            self.ds.fraud_alerts.append(
                {
                    "id": self.new_id(),
                    "transaction_id": t["id"],
                    "customer_id": t["_customer_id"],
                    "rule": "R2_MONTO_ATIPICO",
                    "score": Decimal(str(round(rng.uniform(70, 95), 2))),
                    "source": "RULES",
                    "status": "ABIERTA",
                    "details": {"descripcion": rules[0][1]},
                    "resolved_by": None,
                    "resolved_at": None,
                    "created_at": t["created_at"] + timedelta(seconds=2),
                }
            )

    def make_complaints(self) -> None:
        rng = self.rng
        approved = [c for c in self.ds.customers if c["kyc_status"] == "APROBADO"]
        categories = list(cat.COMPLAINT_TEMPLATES)
        weights = (0.16, 0.22, 0.18, 0.14, 0.2, 0.1)
        injection_slots = set(rng.sample(range(N_COMPLAINTS), len(cat.INJECTION_COMPLAINTS)))
        injections = iter(cat.INJECTION_COMPLAINTS)
        for i in range(N_COMPLAINTS):
            c = rng.choice(approved)
            created = self.rand_dt(self.now - timedelta(days=90), self.now)
            injected = i in injection_slots
            if injected:
                subject, body = next(injections)
                true_cat = "OTRO"
            else:
                true_cat = rng.choices(categories, weights=weights)[0]
                subject, tpl = rng.choice(cat.COMPLAINT_TEMPLATES[true_cat])
                body = tpl.format(
                    amt=f"{rng.uniform(50, 2500):,.2f}",
                    small=f"{rng.uniform(4, 35):,.2f}",
                    merchant=rng.choice(cat.MERCHANTS_POS + cat.MERCHANTS_ONLINE),
                    service=rng.choice(cat.SERVICES),
                    city=rng.choice(cat.REGIONS).cities[0],
                    day=(created - timedelta(days=rng.randint(1, 6))).strftime("%d/%m"),
                )
            if injected:
                ai_cat, confidence, suspicious = "OTRO", rng.uniform(0.3, 0.6), True
            elif rng.random() < 0.88:
                ai_cat, confidence, suspicious = true_cat, rng.uniform(0.72, 0.99), False
            else:
                ai_cat, confidence, suspicious = (
                    rng.choice(categories),
                    rng.uniform(0.5, 0.82),
                    False,
                )
            requires_review = ai_cat == "FRAUDE" or confidence < 0.8 or suspicious
            age = (self.now - created).days
            if age > 20:
                status = "RESUELTA"
            elif age > 5:
                status = rng.choice(("EN_REVISION", "RESUELTA"))
            else:
                status = rng.choice(("NUEVA", "NUEVA", "EN_REVISION"))
            resolved = status == "RESUELTA"
            cid = self.new_id()
            self.ds.complaints.append(
                {
                    "id": cid,
                    "customer_id": c["id"],
                    "subject": subject,
                    "body": body,
                    "channel": rng.choice(("APP", "APP", "APP", "WEB", "TELEFONO")),
                    "status": status,
                    "ai_category": ai_cat,
                    "ai_urgency": "ALTA" if suspicious else cat.URGENCY_BY_CATEGORY[ai_cat],
                    "ai_confidence": Decimal(str(round(confidence, 3))),
                    "ai_reason": "Posible intento de manipulación del sistema"
                    if suspicious
                    else f"El texto describe un caso de {ai_cat.replace('_', ' ').lower()}",
                    "ai_suspicious": suspicious,
                    "requires_review": requires_review,
                    "final_category": true_cat if resolved else None,
                    "reviewed_by": "atencion.demo" if resolved else None,
                    "reviewed_at": created + timedelta(days=rng.randint(1, 10))
                    if resolved
                    else None,
                    "created_at": created,
                    "due_at": regulatory_deadline(created, 15),
                }
            )
            self.ds.ai_interactions.append(
                {
                    "id": self.new_id(),
                    "use_case": "complaint_classification",
                    "prompt_id": "complaint_classifier",
                    "prompt_version": "1.0.0",
                    "input_redacted": None,
                    "output": {
                        "complaint_id": str(cid),
                        "categoria": ai_cat,
                        "sospechosa": suspicious,
                    },
                    "latency_ms": rng.randint(600, 2400),
                    "tokens_in": rng.randint(450, 900),
                    "tokens_out": rng.randint(40, 90),
                    "confidence": Decimal(str(round(confidence, 3))),
                    "blocked_by_shields": injected,
                    "human_override": (true_cat != ai_cat) if resolved else None,
                    "provider": "seed",
                    "created_at": created + timedelta(seconds=2),
                }
            )

    def make_kyc_documents(self) -> None:
        for c in self.ds.customers:
            if c["kyc_status"] == "RECHAZADO" or (
                c["kyc_status"] == "APROBADO" and self.rng.random() > 0.05
            ):
                continue
            mismatch = self.rng.random() < 0.2
            confidence = self.rng.uniform(0.55, 0.78) if mismatch else self.rng.uniform(0.86, 0.99)
            number = c["document_number"]
            if mismatch:
                number = number[:-1] + str((int(number[-1]) + 3) % 10)
            did = self.new_id()
            self.ds.kyc_documents.append(
                {
                    "id": did,
                    "customer_id": c["id"],
                    "blob_path": f"kyc/{c['id']}/{did}.jpg",
                    "extracted_json": {
                        "numero_documento": number,
                        "nombres": c["first_name"].upper(),
                        "apellidos": c["last_name"].upper(),
                        "fecha_nacimiento": c["birth_date"].isoformat(),
                        "fecha_expiracion": (c["created_at"] + timedelta(days=365 * 6))
                        .date()
                        .isoformat(),
                        "modelo": "seed",
                    },
                    "extraction_confidence": Decimal(str(round(confidence, 3))),
                    "created_at": c["created_at"] + timedelta(seconds=30),
                }
            )

    def make_pipeline_history(self) -> None:
        rng = self.rng
        checks = (
            ("ids_no_nulos", "silver.transactions"),
            ("montos_positivos", "silver.transactions"),
            ("moneda_valida", "silver.transactions"),
            ("fecha_no_futura", "silver.transactions"),
            ("sin_duplicados", "silver.transactions"),
            ("cuenta_existe", "silver.transactions"),
        )
        for d in range(14, 0, -1):
            started = datetime.combine((self.now - timedelta(days=d)).date(), time(7, 0), UTC)
            rows_in = rng.randint(280, 420)
            outcome = rng.choices(("EXITOSO", "CON_ALERTAS", "FALLIDO"), weights=(0.8, 0.14, 0.06))[
                0
            ]
            quarantined = rng.randint(1, 6) if outcome == "CON_ALERTAS" else 0
            run_id = self.new_id()
            self.ds.pipeline_runs.append(
                {
                    "id": run_id,
                    "flow_name": "ingesta_transacciones_diaria",
                    "status": outcome,
                    "trigger": "PROGRAMADO",
                    "started_at": started,
                    "finished_at": started + timedelta(minutes=rng.randint(2, 9)),
                    "rows_in": rows_in if outcome != "FALLIDO" else 0,
                    "rows_ok": rows_in - quarantined if outcome != "FALLIDO" else 0,
                    "rows_quarantined": quarantined,
                    "error": "Timeout al conectar con la fuente bronze"
                    if outcome == "FALLIDO"
                    else None,
                }
            )
            if outcome == "FALLIDO":
                continue
            failing = rng.choice(checks[1:4]) if quarantined else None
            for name, table in checks:
                bad = failing is not None and name == failing[0]
                self.ds.quality_checks.append(
                    {
                        "run_id": run_id,
                        "check_name": name,
                        "table_name": table,
                        "passed": not bad,
                        "failed_count": quarantined if bad else 0,
                    }
                )
            for _ in range(quarantined):
                self.ds.quarantine.append(
                    {
                        "run_id": run_id,
                        "raw_id": None,
                        "table_name": "silver.transactions",
                        "reason": f"Falló el check {failing[0] if failing else 'desconocido'}",
                        "payload": {"amount": -round(rng.uniform(10, 500), 2), "currency": "PEN"},
                        "created_at": started + timedelta(minutes=2),
                    }
                )


# Relative weight of each UTC hour (Peru is UTC-5): busy from 12:00 to 03:00 UTC.
_HOUR_WEIGHTS = [6, 4, 3, 1, 1, 1, 1, 1, 1, 1, 1, 2, 5, 7, 8, 8, 9, 10, 9, 9, 8, 9, 10, 8]

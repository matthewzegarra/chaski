"""Builds the gold layer (dimensions + facts) from a generated Dataset.

In Azure this layer is produced by the Prefect/Fabric pipelines into Azure SQL; locally the
simulator fills the `gold` schema so Chaski Insights and NL2SQL have data to work with.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from chaski_simulator import catalog as cat
from chaski_simulator.generate import (
    USD_PEN,
    Dataset,
    balance_after,
    money,
    monthly_rate,
    months_between,
)

MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
PRODUCTS = (
    (1, "AHORRO_SOLES", "Cuenta de ahorro soles", "PASIVO"),
    (2, "AHORRO_DOLARES", "Cuenta de ahorro dólares", "PASIVO"),
    (3, "PRESTAMO_CONSUMO", "Préstamo de consumo", "ACTIVO"),
    (4, "TARJETA_CREDITO", "Tarjeta de crédito", "ACTIVO"),
)
FTP_RATE = 0.06  # internal yield credited to deposits
FUNDING_RATE = 0.05  # cost of funds charged to loans and cards


def month_start(d: date) -> date:
    return d.replace(day=1)


def age_band(birth: date, today: date) -> str:
    age = (today - birth).days // 365
    if age <= 25:
        return "18-25"
    if age <= 35:
        return "26-35"
    if age <= 45:
        return "36-45"
    if age <= 60:
        return "46-60"
    return "60+"


def build_gold(ds: Dataset) -> dict[str, list[tuple[Any, ...]]]:
    today = ds.now.date()
    window_start = today - timedelta(days=182)
    customers = {c["id"]: c for c in ds.customers}
    out: dict[str, list[tuple[Any, ...]]] = {}

    # ---- dimensions
    out["gold.dim_date"] = []
    d = today - timedelta(days=730)
    while d <= today:
        out["gold.dim_date"].append(
            (
                int(d.strftime("%Y%m%d")),
                d,
                d.year,
                (d.month - 1) // 3 + 1,
                d.month,
                MONTH_NAMES[d.month - 1],
                d.isoweekday(),
                d.isoweekday() >= 6,
            )
        )
        d += timedelta(days=1)
    out["gold.dim_region"] = [(i + 1, r.name, r.macro) for i, r in enumerate(cat.REGIONS)]
    out["gold.dim_product"] = list(PRODUCTS)

    balances: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for a in ds.accounts:
        bal = a["balance"] * (USD_PEN if a["currency"] == "USD" else 1)
        balances[a["customer_id"]] += bal
    active_loans: dict[uuid.UUID, int] = defaultdict(int)
    for loan in ds.loans:
        if loan["status"] == "DESEMBOLSADO":
            active_loans[loan["customer_id"]] += 1
    out["gold.dim_customer"] = [
        (
            c["id"],
            c["segment"],
            c["region"],
            age_band(c["birth_date"], today),
            c["kyc_status"],
            month_start(c["created_at"].date()),
            money(balances[c["id"]]),
            active_loans[c["id"]],
        )
        for c in ds.customers
    ]

    # ---- portfolio daily (disbursed loans only)
    portfolio: list[tuple[Any, ...]] = []
    loan_month: dict[tuple[uuid.UUID, date], list[tuple[float, str]]] = defaultdict(list)
    for loan in ds.loans:
        if loan["status"] != "DESEMBOLSADO":
            continue
        disbursed = loan["disbursed_at"]
        amount, tea, term = float(loan["amount"]), float(loan["rate_tea"]), loan["term_months"]
        final_dpd = ds.loan_final_dpd.get(loan["id"], 0)
        day = max(window_start, disbursed.date())
        while day <= today:
            dpd = max(0, final_dpd - (today - day).days)
            elapsed = min(
                term, months_between(disbursed, ds.now - timedelta(days=(today - day).days))
            )
            paid = max(0, elapsed - (math.ceil(dpd / 30) if dpd else 0))
            outstanding = balance_after(amount, tea, term, paid)
            bucket = cat.bucket_for(dpd)
            portfolio.append(
                (
                    loan["id"],
                    day,
                    money(outstanding),
                    dpd,
                    bucket,
                    loan["_region"],
                    loan["_segment"],
                )
            )
            loan_month[(loan["id"], month_start(day))].append((outstanding, bucket))
            day += timedelta(days=1)
    out["gold.fact_portfolio_daily"] = portfolio

    # ---- profitability monthly
    acc_rows: dict[tuple[str, str, str, date], dict[str, float]] = defaultdict(
        lambda: {"interest_income": 0.0, "fees": 0.0, "funding_cost": 0.0, "provisions": 0.0}
    )
    months = []
    m = month_start(window_start)
    while m <= today:
        months.append(m)
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)

    # Deposits: replay each account to get month-end balances.
    tx_by_account: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for t in ds.transactions:
        tx_by_account[t["account_id"]].append(t)
    credit_types = {"DEPOSITO", "TRANSFERENCIA_IN", "INTERES"}
    for a in ds.accounts:
        fx = float(USD_PEN) if a["currency"] == "USD" else 1.0
        bal = 0.0
        month_end_balance: dict[date, float] = {}
        for t in tx_by_account[a["id"]]:
            amt = float(t["amount"])
            bal += amt if t["type"] in credit_types else -amt
            month = month_start(t["created_at"].date())
            month_end_balance[month] = bal
            key = (a["product"], a["_segment"], a["_region"], month)
            if t["type"] == "COMISION":
                acc_rows[key]["fees"] += amt * fx
            elif t["type"] == "INTERES":
                acc_rows[key]["funding_cost"] += amt * fx
        last = 0.0
        for month in months:
            last = month_end_balance.get(month, last)
            if last > 0:
                acc_rows[(a["product"], a["_segment"], a["_region"], month)]["interest_income"] += (
                    last * fx * FTP_RATE / 12
                )

    loans_by_id = {loan["id"]: loan for loan in ds.loans}
    for (loan_id, month), points in loan_month.items():
        loan = loans_by_id[loan_id]
        avg_out = sum(p[0] for p in points) / len(points)
        bucket = points[-1][1]
        key = ("PRESTAMO_CONSUMO", loan["_segment"], loan["_region"], month)
        acc_rows[key]["interest_income"] += avg_out * monthly_rate(float(loan["rate_tea"]))
        acc_rows[key]["funding_cost"] += avg_out * FUNDING_RATE / 12
        acc_rows[key]["provisions"] += avg_out * cat.provision_rate(bucket) * 0.1
        if month_start(loan["disbursed_at"].date()) == month:
            acc_rows[key]["fees"] += float(loan["amount"]) * 0.01

    for card in ds.cards:
        if card["type"] != "CREDITO" or card["credit_limit"] is None:
            continue
        c = customers[card["customer_id"]]
        used = float(card["credit_limit"]) * ds.card_utilisation.get(card["id"], 0.4)
        for month in months:
            if month_start(card["created_at"].date()) > month:
                continue
            key = ("TARJETA_CREDITO", c["segment"], c["region"], month)
            acc_rows[key]["interest_income"] += used * 0.035
            acc_rows[key]["fees"] += 10.0
            acc_rows[key]["funding_cost"] += used * FUNDING_RATE / 12
            acc_rows[key]["provisions"] += used * 0.02 / 12

    out["gold.fact_profitability_monthly"] = [
        (
            product,
            segment,
            region,
            month,
            money(v["interest_income"]),
            money(v["fees"]),
            money(v["funding_cost"]),
            money(v["provisions"]),
            money(v["interest_income"] + v["fees"] - v["funding_cost"] - v["provisions"]),
        )
        for (product, segment, region, month), v in sorted(acc_rows.items())
    ]
    return out

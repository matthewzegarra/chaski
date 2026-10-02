"""CLI: python -m chaski_simulator [--reset] [--seed 42] [--live]."""

from __future__ import annotations

import argparse
import os
import time

from chaski_simulator.generate import Generator
from chaski_simulator.live import run_live
from chaski_simulator.loader import load


def main() -> None:
    parser = argparse.ArgumentParser(description="CHASKI synthetic data generator")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--reset", action="store_true", help="truncate core/ops/gold before loading"
    )
    parser.add_argument(
        "--live", action="store_true", help="generate continuous transactions via cuentas-api"
    )
    parser.add_argument(
        "--interval", type=float, default=3.0, help="seconds between live transactions"
    )
    args = parser.parse_args()

    db_url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not db_url:
        raise SystemExit("MIGRATIONS_DATABASE_URL is not set")

    if args.live:
        run_live(
            db_url,
            os.environ.get("CUENTAS_API_URL", "http://localhost:8001"),
            os.environ.get("CORE_API_URL", "http://localhost:8002"),
            args.interval,
            None,
        )
        return

    t0 = time.perf_counter()
    dataset = Generator(seed=args.seed).run()
    t1 = time.perf_counter()
    counts = load(dataset, db_url, reset=args.reset)
    t2 = time.perf_counter()
    width = max(len(k) for k in counts)
    for table, n in counts.items():
        print(f"  {table:<{width}}  {n:>7,}")
    print(f"Generated in {t1 - t0:.1f}s, loaded in {t2 - t1:.1f}s (seed={args.seed}).")


if __name__ == "__main__":
    main()

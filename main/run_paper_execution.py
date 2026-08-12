"""CLI launcher for the persistent paper-only execution ledger."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from swing_trade_bot.paper_execution_engine import execute_allocations


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Swing allocations to the paper ledger")
    parser.add_argument("--allocations", type=Path, default=Path("results/portfolio_allocations.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--state-dir", type=Path, default=Path("results/paper_ledger"))
    parser.add_argument("--account-capital", type=float, required=True)
    args = parser.parse_args()
    report = execute_allocations(
        allocations_path=args.allocations,
        data_dir=args.data_dir,
        state_dir=args.state_dir,
        account_capital=args.account_capital,
    )
    print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    main()

"""Initialize and optionally populate the authoritative SWING-001 paper ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from swing_trade_bot.paper_execution_engine import execute_allocations
from swing_trade_bot.paper_ledger_foundation import SWING_ALLOCATION, initialize_paper_ledger


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Phase 2.1 SWING-001 paper ledger.")
    parser.add_argument("--ledger-dir", default="results/paper_ledger")
    parser.add_argument("--allocations-file", default="results/portfolio_allocations.json")
    parser.add_argument("--market-data-dir", default="results/enterprise_market_data")
    parser.add_argument("--initialize-only", action="store_true")
    args = parser.parse_args()

    ledger_dir = Path(args.ledger_dir)
    initialize_paper_ledger(ledger_dir)

    if not args.initialize_only:
        execute_allocations(
            allocations_path=Path(args.allocations_file),
            data_dir=Path(args.market_data_dir),
            state_dir=ledger_dir,
            account_capital=SWING_ALLOCATION,
        )

    status = initialize_paper_ledger(ledger_dir)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI launcher for paper-only portfolio mark-to-market reporting."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from swing_trade_bot.paper_portfolio_manager import build_and_write_paper_portfolio_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Value the persistent Swing paper portfolio.")
    parser.add_argument("--ledger-dir", default="results/paper_ledger")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output-dir", default="results/paper_ledger")
    parser.add_argument("--account-capital", type=float, required=True)
    args = parser.parse_args()

    report = build_and_write_paper_portfolio_report(
        ledger_dir=Path(args.ledger_dir),
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        account_capital=args.account_capital,
    )
    payload = {key: value for key, value in asdict(report).items() if key != "positions"}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI launcher for SWING-001 paper portfolio valuation.

Production mode consumes normalized AI CIO Enterprise Market Data Provider v1.0
evidence. Local CSV use is available only through explicit fixture mode.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from swing_trade_bot.enterprise_market_data_client import EnterpriseMarketDataClient, MarketDataUnavailable
from swing_trade_bot.enterprise_paper_portfolio_manager import (
    build_and_write_enterprise_paper_portfolio_report,
    write_blocked_state,
)
from swing_trade_bot.paper_portfolio_manager import build_and_write_paper_portfolio_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Value the persistent SWING-001 paper portfolio.")
    parser.add_argument("--ledger-dir", default="results/paper_ledger")
    parser.add_argument("--output-dir", default="results/paper_ledger")
    parser.add_argument("--account-capital", type=float, required=True)
    parser.add_argument(
        "--contract-path",
        default="/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_contract.json",
    )
    parser.add_argument(
        "--status-path",
        default="/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_status.json",
    )
    parser.add_argument(
        "--fixture-csv-mode",
        action="store_true",
        help="Explicit test/sample/archive mode; never a production fallback",
    )
    parser.add_argument("--data-dir", default="data", help="Used only with --fixture-csv-mode")
    args = parser.parse_args()

    ledger_dir = Path(args.ledger_dir)
    output_dir = Path(args.output_dir)
    try:
        if args.fixture_csv_mode:
            report = build_and_write_paper_portfolio_report(
                ledger_dir=ledger_dir,
                data_dir=Path(args.data_dir),
                output_dir=output_dir,
                account_capital=args.account_capital,
            )
        else:
            client = EnterpriseMarketDataClient(
                contract_path=Path(args.contract_path),
                status_path=Path(args.status_path),
            )
            report = build_and_write_enterprise_paper_portfolio_report(
                ledger_dir=ledger_dir,
                output_dir=output_dir,
                account_capital=args.account_capital,
                client=client,
            )
    except MarketDataUnavailable as exc:
        path = write_blocked_state(output_dir, exc)
        print(json.dumps({"strategy_id": "SWING-001", "status": "BLOCKED", "artifact": str(path), "reason": str(exc)}, indent=2))
        return 2

    payload = {key: value for key, value in asdict(report).items() if key != "positions"}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

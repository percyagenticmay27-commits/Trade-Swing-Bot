"""Materialize fresh AI CIO normalized history for existing Swing analytics.

This writes only to results/enterprise_market_data; it never falls back to the
legacy production data directory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from swing_trade_bot.enterprise_market_data_client import EnterpriseMarketDataClient, MarketDataUnavailable
from swing_trade_bot.enterprise_paper_portfolio_manager import write_blocked_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-path", default="/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_contract.json")
    parser.add_argument("--status-path", default="/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_status.json")
    parser.add_argument("--output-dir", default="results/enterprise_market_data")
    parser.add_argument("--required-symbol", action="append", default=["SOXL", "TQQQ"])
    parser.add_argument("--optional-symbol", action="append", default=[])
    args = parser.parse_args()
    output = Path(args.output_dir)
    try:
        client = EnterpriseMarketDataClient(contract_path=Path(args.contract_path), status_path=Path(args.status_path))
        written = []
        for symbol in dict.fromkeys(args.required_symbol):
            path = client.write_history_csv(symbol, output / f"{symbol.upper()}.csv", required=True)
            written.append(str(path))
        for symbol in dict.fromkeys(args.optional_symbol):
            path = client.write_history_csv(symbol, output / f"{symbol.upper()}.csv", required=False)
            if path is not None: written.append(str(path))
        status = {"strategy_id": "SWING-001", "status": "READY" if not client.warnings else "WARNING", "normalized_history_files": written, "warnings": client.warnings}
        (output / "sync_status.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0
    except MarketDataUnavailable as exc:
        path = write_blocked_state(Path("results/paper_ledger"), exc)
        print(json.dumps({"strategy_id": "SWING-001", "status": "BLOCKED", "artifact": str(path), "reason": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

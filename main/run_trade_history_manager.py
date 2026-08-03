"""CLI launcher for the paper-only Trade History Manager."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from swing_trade_bot.trade_history_manager import build_and_write_trade_history_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build paper trade lifecycle evidence.")
    parser.add_argument(
        "--trade-history",
        type=Path,
        default=Path("results/paper_ledger/trade_history.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/paper_ledger"),
    )
    args = parser.parse_args()
    report = build_and_write_trade_history_report(
        trade_history_path=args.trade_history,
        output_dir=args.output_dir,
    )
    summary = {
        key: value
        for key, value in asdict(report).items()
        if key not in {"trades", "open_lots", "closed_trades"}
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

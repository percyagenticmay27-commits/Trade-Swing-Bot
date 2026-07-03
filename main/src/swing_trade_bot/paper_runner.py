"""Command-line runner for CSV-backed paper strategy evaluations."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .engine import SwingTradeEngine
from .position_state import MarketBar


def load_csv(path: Path) -> list[MarketBar]:
    """Load chronological daily bars from a date,close,volume CSV file."""
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        required = {"date", "close", "volume"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain date, close, and volume columns")
        bars = [
            MarketBar(
                date=date.fromisoformat(row["date"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                open=_optional_float(row.get("open")),
                high=_optional_float(row.get("high")),
                low=_optional_float(row.get("low")),
            )
            for row in reader
        ]
    return bars


def _optional_float(value: str | None) -> float | None:
    return None if value is None or not value.strip() else float(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the paper swing strategy from CSV data")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--account-value", type=float, required=True)
    args = parser.parse_args()

    engine = SwingTradeEngine(account_value=args.account_value)
    required_symbols = (*engine.config.symbols, "SPY", "QQQ")
    market_data = {
        symbol: load_csv(args.data_dir / f"{symbol}.csv")
        for symbol in required_symbols
    }
    results = engine.evaluate_all(market_data)
    print(json.dumps([asdict(result) for result in results], indent=2))


if __name__ == "__main__":
    main()

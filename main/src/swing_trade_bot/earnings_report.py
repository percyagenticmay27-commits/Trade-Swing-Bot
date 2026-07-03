"""Standalone paper-only earnings risk report writer."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EarningsRow:
    symbol: str
    earnings_date: str
    days_until_earnings: int | None
    earnings_risk_level: str
    action: str


def build_earnings_report(input_path: Path, output_dir: Path, *, as_of: date | None = None, paper_trade_mode: bool = True) -> list[EarningsRow]:
    if not paper_trade_mode:
        raise ValueError("Earnings report requires paper_trade_mode=True")
    rows = read_earnings_rows(input_path, as_of=as_of or date.today())
    write_earnings_report(output_dir, rows)
    return rows


def read_earnings_rows(path: Path, *, as_of: date) -> list[EarningsRow]:
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        rows = []
        for row in csv.DictReader(input_file):
            earnings_date = row.get("earnings_date", "").strip()
            days = None
            if earnings_date:
                days = (date.fromisoformat(earnings_date) - as_of).days
            risk = _risk_level(days)
            rows.append(EarningsRow(row.get("symbol", row.get("underlying_symbol", "")).upper(), earnings_date, days, risk, _action(risk)))
        return rows


def write_earnings_report(output_dir: Path, rows: list[EarningsRow]) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "earnings_report.csv"
    json_path = output_dir / "earnings_report.json"
    md_path = output_dir / "earnings_report.md"
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(EarningsRow.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    json_path.write_text(json.dumps({"paper_trade_mode": True, "rows": [asdict(row) for row in rows]}, indent=2) + "\n", encoding="utf-8")
    lines = ["# Earnings Report", "", "Paper-only: true", "", "| Symbol | Earnings Date | Days | Risk | Action |", "|---|---:|---:|---|---|"]
    lines.extend(f"| {row.symbol} | {row.earnings_date or '-'} | {'' if row.days_until_earnings is None else row.days_until_earnings} | {row.earnings_risk_level} | {row.action} |" for row in rows)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a paper-only earnings risk report")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    build_earnings_report(args.input, args.output_dir, as_of=args.as_of, paper_trade_mode=True)


def _risk_level(days: int | None) -> str:
    if days is None:
        return "UNKNOWN"
    if 0 <= days <= 7:
        return "HIGH"
    if 8 <= days <= 14:
        return "MEDIUM"
    if days < 0:
        return "PAST"
    return "LOW"


def _action(risk: str) -> str:
    return {
        "HIGH": "Avoid new entry or reduce paper exposure before earnings.",
        "MEDIUM": "Review position sizing and stop risk.",
        "LOW": "No earnings restriction.",
        "PAST": "Refresh next earnings date.",
        "UNKNOWN": "Add earnings date evidence.",
    }[risk]


if __name__ == "__main__":
    main()

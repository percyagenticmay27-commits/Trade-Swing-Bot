"""Confidence promotion and demotion rules for allocation control."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .allocation_engine import FORCED_CONFIDENCE


@dataclass(frozen=True, slots=True)
class ConfidenceRow:
    """One symbol confidence evaluation."""

    symbol: str
    confidence: str
    win_rate: float | None
    profit_factor: float | None
    trade_count: int
    trading_days: int
    promotion_eligible: bool
    demotion_eligible: bool


def build_confidence_report(
    scores_path: Path,
    data_dir: Path,
    *,
    output_dir: Path | None = None,
    starting_confidence: dict[str, str] | None = None,
    candidate_symbols: list[str] | tuple[str, ...] | set[str] | None = None,
    paper_trade_mode: bool = True,
) -> list[ConfidenceRow]:
    """Evaluate confidence for the current evidence-driven candidate universe.

    The confidence universe is no longer the legacy static allocation universe.
    Symbols are discovered from current performance evidence, explicit starting
    confidence, and optional current candidate symbols. Legacy forced-confidence
    values are retained only as starting labels for matching discovered symbols.
    """
    if not paper_trade_mode:
        raise ValueError("Confidence engine requires paper_trade_mode=True")
    metrics = _read_metrics(scores_path)
    explicit_confidence = {
        symbol.upper(): value.upper()
        for symbol, value in (starting_confidence or {}).items()
    }
    universe = _confidence_universe(
        metrics=metrics,
        starting_confidence=explicit_confidence,
        candidate_symbols=candidate_symbols,
    )
    rows = [
        _evaluate_symbol(
            symbol,
            explicit_confidence.get(symbol, FORCED_CONFIDENCE.get(symbol, "LOW")),
            metrics.get(symbol),
            _trading_days(data_dir, symbol),
        )
        for symbol in universe
    ]
    write_confidence_reports(output_dir or scores_path.parent, rows)
    return rows


def write_confidence_reports(output_dir: Path, rows: list[ConfidenceRow]) -> tuple[Path, Path]:
    """Write confidence_report.csv and confidence_report.json."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "confidence_report.csv"
    json_path = output_dir / "confidence_report.json"
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "symbol",
                "confidence",
                "win_rate",
                "profit_factor",
                "trade_count",
                "trading_days",
                "promotion_eligible",
                "demotion_eligible",
            ],
        )
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    json_path.write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "universe_source": "CURRENT_EVIDENCE_AND_CANDIDATES",
                "legacy_static_universe_enabled": False,
                "promotion_rules": {
                    "LOW_to_MEDIUM": {
                        "win_rate_min": 40.0,
                        "profit_factor_min": 1.50,
                        "trade_count_min": 15,
                        "trading_days_min": 252,
                    },
                    "MEDIUM_to_HIGH": {
                        "win_rate_min": 50.0,
                        "profit_factor_min": 2.00,
                        "trade_count_min": 25,
                        "trading_days_min": 504,
                    },
                },
                "demotion_rules": {
                    "HIGH_to_MEDIUM": {"win_rate_lt": 45.0, "profit_factor_lt": 1.50},
                    "MEDIUM_to_LOW": {"win_rate_lt": 35.0, "profit_factor_lt": 1.25},
                },
                "rows": [asdict(row) for row in rows],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return csv_path, json_path


def format_confidence_table(rows: list[ConfidenceRow]) -> str:
    headers = ("Symbol", "Confidence", "Win Rate", "Profit Factor", "Trades", "Days", "Promote", "Demote")
    table_rows = [
        (
            row.symbol,
            row.confidence,
            _number(row.win_rate),
            _number(row.profit_factor),
            str(row.trade_count),
            str(row.trading_days),
            "yes" if row.promotion_eligible else "no",
            "yes" if row.demotion_eligible else "no",
        )
        for row in rows
    ]
    if not table_rows:
        return "  ".join(headers)
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in table_rows))
        for index in range(len(headers))
    ]
    lines = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in table_rows
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate confidence promotion and demotion status")
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--candidate-symbol",
        action="append",
        default=[],
        help="Optional current candidate symbol. Can be provided multiple times.",
    )
    args = parser.parse_args()

    rows = build_confidence_report(
        args.scores,
        args.data_dir,
        output_dir=args.output_dir,
        candidate_symbols=args.candidate_symbol,
        paper_trade_mode=True,
    )
    print(format_confidence_table(rows))


def _confidence_universe(
    *,
    metrics: dict[str, dict[str, float]],
    starting_confidence: dict[str, str],
    candidate_symbols: list[str] | tuple[str, ...] | set[str] | None,
) -> tuple[str, ...]:
    """Return deterministic current symbols without importing the legacy universe."""
    symbols = set(metrics) | set(starting_confidence)
    symbols.update(
        str(symbol).strip().upper()
        for symbol in (candidate_symbols or ())
        if str(symbol).strip()
    )
    return tuple(sorted(symbols))


def _evaluate_symbol(
    symbol: str,
    confidence: str,
    metrics: dict[str, float] | None,
    trading_days: int,
) -> ConfidenceRow:
    win_rate = metrics.get("win_rate") if metrics else None
    profit_factor = metrics.get("profit_factor") if metrics else None
    trade_count = int(metrics.get("number_of_trades", 0)) if metrics else 0
    promotion_eligible = _promotion_eligible(confidence, win_rate, profit_factor, trade_count, trading_days)
    demotion_eligible = _demotion_eligible(confidence, win_rate, profit_factor)
    return ConfidenceRow(
        symbol=symbol,
        confidence=confidence,
        win_rate=win_rate,
        profit_factor=profit_factor,
        trade_count=trade_count,
        trading_days=trading_days,
        promotion_eligible=promotion_eligible,
        demotion_eligible=demotion_eligible,
    )


def _promotion_eligible(
    confidence: str,
    win_rate: float | None,
    profit_factor: float | None,
    trade_count: int,
    trading_days: int,
) -> bool:
    if win_rate is None or profit_factor is None:
        return False
    if confidence == "LOW":
        return win_rate >= 40.0 and profit_factor >= 1.50 and trade_count >= 15 and trading_days >= 252
    if confidence == "MEDIUM":
        return win_rate >= 50.0 and profit_factor >= 2.00 and trade_count >= 25 and trading_days >= 504
    return False


def _demotion_eligible(confidence: str, win_rate: float | None, profit_factor: float | None) -> bool:
    if win_rate is None or profit_factor is None:
        return False
    if confidence == "HIGH":
        return win_rate < 45.0 or profit_factor < 1.50
    if confidence == "MEDIUM":
        return win_rate < 35.0 or profit_factor < 1.25
    return False


def _read_metrics(path: Path) -> dict[str, dict[str, float]]:
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        metrics: dict[str, dict[str, float]] = {}
        for row in reader:
            symbol = row["symbol"].strip().upper()
            metrics[symbol] = {
                "win_rate": float(row["win_rate"]),
                "profit_factor": float(row["profit_factor"]),
                "number_of_trades": float(row["number_of_trades"]),
            }
    return metrics


def _trading_days(data_dir: Path, symbol: str) -> int:
    path = data_dir / f"{symbol}.csv"
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return max(sum(1 for _ in input_file) - 1, 0)


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


if __name__ == "__main__":
    main()

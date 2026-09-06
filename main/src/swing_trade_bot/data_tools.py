"""Historical CSV validation tools for optimization data prep."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import StrategyConfig
from .market_symbol_mapping import known_inception_date


REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")
REQUIRED_SYMBOLS = (*StrategyConfig().symbols, "SPY", "QQQ")
MINIMUM_BARS = 252
MINIMUM_SIGNAL_BARS = 50


@dataclass(frozen=True, slots=True)
class SymbolValidation:
    symbol: str
    path: Path
    exists: bool
    row_count: int = 0
    start_date: date | None = None
    end_date: date | None = None
    required_bars: int = MINIMUM_BARS
    invalid_rows: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.exists and not self.invalid_rows


def required_bars_for_symbol(symbol: str, *, as_of: date | None = None) -> int:
    """Return listing-age-aware history floor while preserving 50-bar signal evidence."""
    inception = known_inception_date(symbol)
    if inception is None:
        return MINIMUM_BARS
    today = as_of or date.today()
    if today <= inception:
        return MINIMUM_SIGNAL_BARS
    approximate_sessions = max(0, int((today - inception).days * 5 / 7) - 5)
    return max(MINIMUM_SIGNAL_BARS, min(MINIMUM_BARS, approximate_sessions))


def validate_data_directory(
    data_dir: Path,
    *,
    as_of: date | None = None,
    symbols: tuple[str, ...] = REQUIRED_SYMBOLS,
) -> list[SymbolValidation]:
    """Validate OHLCV CSV files for the requested evidence symbols."""
    return [
        _validate_symbol_csv(
            symbol,
            data_dir / f"{symbol}.csv",
            required_bars=required_bars_for_symbol(symbol, as_of=as_of),
        )
        for symbol in symbols
    ]


def format_validation_summary(results: list[SymbolValidation]) -> str:
    missing = [result.symbol for result in results if not result.exists]
    invalid = [result for result in results if result.invalid_rows]
    required_symbols = [result.symbol for result in results]
    lines = [
        "Historical data validation summary",
        f"Required symbols: {', '.join(required_symbols)}",
        f"Missing files: {', '.join(missing) if missing else 'none'}",
        f"Invalid symbols: {', '.join(result.symbol for result in invalid) if invalid else 'none'}",
        "",
        "Symbol  Rows  Required  Start Date  End Date    Status",
        "------  ----  --------  ----------  ----------  ------",
    ]
    for result in results:
        start = result.start_date.isoformat() if result.start_date else "-"
        end = result.end_date.isoformat() if result.end_date else "-"
        if not result.exists:
            status = "MISSING"
        elif result.invalid_rows:
            status = f"INVALID ({len(result.invalid_rows)} issue(s))"
        else:
            status = "OK"
        lines.append(
            f"{result.symbol.ljust(6)}  {str(result.row_count).rjust(4)}  "
            f"{str(result.required_bars).rjust(8)}  {start.ljust(10)}  {end.ljust(10)}  {status}"
        )
    if invalid:
        lines.append("")
        lines.append("Invalid rows:")
        for result in invalid:
            lines.append(f"{result.symbol}:")
            lines.extend(f"  - {issue}" for issue in result.invalid_rows)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate optimization OHLCV CSV data")
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    results = validate_data_directory(args.data_dir)
    print(format_validation_summary(results))
    raise SystemExit(0 if all(result.is_valid for result in results) else 1)


def _validate_symbol_csv(symbol: str, path: Path, *, required_bars: int = MINIMUM_BARS) -> SymbolValidation:
    if not path.exists():
        return SymbolValidation(symbol=symbol, path=path, exists=False, required_bars=required_bars)
    invalid_rows: list[str] = []
    parsed_dates: list[date] = []
    row_count = 0
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        missing_columns = _missing_columns(reader.fieldnames)
        if missing_columns:
            invalid_rows.append(f"header: missing columns: {', '.join(missing_columns)}")
            return SymbolValidation(symbol=symbol, path=path, exists=True, row_count=0, required_bars=required_bars, invalid_rows=tuple(invalid_rows))
        previous_date: date | None = None
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            parsed_date, issues = _validate_row(row, row_number)
            invalid_rows.extend(issues)
            if parsed_date is not None:
                parsed_dates.append(parsed_date)
                if previous_date is not None and parsed_date <= previous_date:
                    invalid_rows.append(f"row {row_number}: date is not chronological")
                previous_date = parsed_date
    if row_count < required_bars:
        invalid_rows.append(f"file: expected at least {required_bars} rows, found {row_count}")
    return SymbolValidation(
        symbol=symbol,
        path=path,
        exists=True,
        row_count=row_count,
        start_date=parsed_dates[0] if parsed_dates else None,
        end_date=parsed_dates[-1] if parsed_dates else None,
        required_bars=required_bars,
        invalid_rows=tuple(invalid_rows),
    )


def _missing_columns(fieldnames: list[str] | None) -> list[str]:
    if fieldnames is None:
        return list(REQUIRED_COLUMNS)
    normalized = {field.strip().lower() for field in fieldnames}
    return [column for column in REQUIRED_COLUMNS if column not in normalized]


def _validate_row(row: dict[str, str], row_number: int) -> tuple[date | None, list[str]]:
    issues: list[str] = []
    parsed_date: date | None = None
    try:
        parsed_date = date.fromisoformat(row["date"].strip())
    except (KeyError, ValueError):
        issues.append(f"row {row_number}: invalid date")
    prices: dict[str, float] = {}
    for column in ("open", "high", "low", "close"):
        value = row.get(column, "")
        if value is None or not value.strip():
            issues.append(f"row {row_number}: missing {column}")
            continue
        try:
            prices[column] = float(value)
        except ValueError:
            issues.append(f"row {row_number}: invalid {column}")
            continue
        if prices[column] <= 0:
            issues.append(f"row {row_number}: {column} must be positive")
    volume_value = row.get("volume", "")
    if volume_value is None or not volume_value.strip():
        issues.append(f"row {row_number}: missing volume")
    else:
        try:
            volume = float(volume_value)
            if volume < 0:
                issues.append(f"row {row_number}: volume must be non-negative")
        except ValueError:
            issues.append(f"row {row_number}: invalid volume")
    if {"open", "high", "low", "close"}.issubset(prices):
        if prices["high"] < prices["open"] or prices["high"] < prices["close"]:
            issues.append(f"row {row_number}: high must be >= open and close")
        if prices["low"] > prices["open"] or prices["low"] > prices["close"]:
            issues.append(f"row {row_number}: low must be <= open and close")
    return parsed_date, issues


if __name__ == "__main__":
    main()

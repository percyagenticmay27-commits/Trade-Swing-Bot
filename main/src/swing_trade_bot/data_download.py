"""Market data acquisition for historical OHLCV CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .data_tools import REQUIRED_COLUMNS, REQUIRED_SYMBOLS, format_validation_summary, validate_data_directory


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    """One normalized daily market bar."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class DownloadSummary:
    """Data acquisition status for one symbol."""

    symbol: str
    rows: int
    start_date: date | None
    end_date: date | None
    updated: bool
    source: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadRun:
    """Complete data acquisition result."""

    summaries: tuple[DownloadSummary, ...]
    validation_summary: str
    validation_ok: bool


def build_historical_data(
    data_dir: Path,
    *,
    years: int = 5,
    refresh: bool = False,
    import_dir: Path | None = None,
    symbols: tuple[str, ...] = REQUIRED_SYMBOLS,
) -> DownloadRun:
    """Download, merge, write, and validate historical OHLCV CSVs."""
    if years <= 0:
        raise ValueError("years must be positive")
    data_dir.mkdir(parents=True, exist_ok=True)

    end = date.today()
    start = end - timedelta(days=round(years * 365.25))
    summaries = tuple(
        _update_symbol(symbol, data_dir, start=start, end=end, refresh=refresh, import_dir=import_dir)
        for symbol in symbols
    )
    validations = validate_data_directory(data_dir)
    return DownloadRun(
        summaries=summaries,
        validation_summary=format_validation_summary(validations),
        validation_ok=all(result.is_valid for result in validations),
    )


def format_download_summary(summaries: tuple[DownloadSummary, ...]) -> str:
    """Render the acquisition summary table."""
    lines = [
        "Symbol  Rows  Start Date  End Date    Updated  Source  Error",
        "------  ----  ----------  ----------  -------  ------  -----",
    ]
    for summary in summaries:
        start = summary.start_date.isoformat() if summary.start_date else "-"
        end = summary.end_date.isoformat() if summary.end_date else "-"
        updated = "yes" if summary.updated else "no"
        source = summary.source or "-"
        error = summary.error or "-"
        lines.append(
            f"{summary.symbol.ljust(6)}  {str(summary.rows).rjust(4)}  {start.ljust(10)}  "
            f"{end.ljust(10)}  {updated.ljust(7)}  {source.ljust(6)}  {error}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and maintain historical OHLCV CSV data")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--import-dir", type=Path)
    parser.add_argument("--years", type=int, default=5, choices=(5, 10))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    run = build_historical_data(
        args.data_dir,
        years=args.years,
        refresh=args.refresh,
        import_dir=args.import_dir,
    )
    print(format_download_summary(run.summaries))
    print()
    print(run.validation_summary)
    failed_downloads = any(summary.error for summary in run.summaries)
    raise SystemExit(0 if run.validation_ok and not failed_downloads else 1)


def _update_symbol(
    symbol: str,
    data_dir: Path,
    *,
    start: date,
    end: date,
    refresh: bool,
    import_dir: Path | None,
) -> DownloadSummary:
    path = data_dir / f"{symbol}.csv"
    existing = {} if refresh else _bars_by_date(_load_local_csv(path))
    errors: list[str] = []

    downloaded: list[OHLCVBar] = []
    source: str | None = None
    for provider_name, provider in (
        ("yahoo", _download_yahoo),
        ("yahoo_chart", _download_yahoo_chart),
        ("stooq", _download_stooq),
    ):
        try:
            downloaded = provider(symbol, start, end)
            if downloaded:
                source = provider_name
                break
            errors.append(f"{provider_name}: no rows")
        except (OSError, URLError, ValueError) as exc:
            errors.append(f"{provider_name}: {exc}")

    if not downloaded and import_dir is not None:
        imported = import_dir / f"{symbol}.csv"
        downloaded = _load_local_csv(imported)
        if downloaded:
            source = "csv"
        else:
            errors.append("csv: no rows")

    if not downloaded:
        current = tuple(existing.values())
        return _summary(symbol, current, updated=False, source=None, error="; ".join(errors))

    merged = existing
    before = set(merged)
    merged.update(_bars_by_date(downloaded))
    bars = sorted(merged.values(), key=lambda bar: bar.date)
    _write_csv(path, bars)
    updated = bool(set(merged) - before) or refresh
    return _summary(symbol, bars, updated=updated, source=source, error=None)


def _download_yahoo(symbol: str, start: date, end: date) -> list[OHLCVBar]:
    period1 = int(time.mktime(start.timetuple()))
    period2 = int(time.mktime((end + timedelta(days=1)).timetuple()))
    url = (
        f"https://query1.finance.yahoo.com/v7/finance/download/{symbol}"
        f"?period1={period1}&period2={period2}&interval=1d&events=history&includeAdjustedClose=true"
    )
    return _parse_provider_csv(_read_url(url))


def _download_yahoo_chart(symbol: str, start: date, end: date) -> list[OHLCVBar]:
    period1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()) + 24 * 60 * 60
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={period1}&period2={period2}&interval=1d&events=history"
    )
    payload = json.loads(_read_url(url))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if result is None:
        error = payload.get("chart", {}).get("error") or {}
        raise ValueError(error.get("description", "no chart result"))
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [None])[0]
    if quote is None:
        raise ValueError("no chart quote data")

    bars: list[OHLCVBar] = []
    for index, timestamp in enumerate(timestamps):
        try:
            values = {
                "open": quote["open"][index],
                "high": quote["high"][index],
                "low": quote["low"][index],
                "close": quote["close"][index],
                "volume": quote["volume"][index],
            }
        except (KeyError, IndexError) as exc:
            raise ValueError("malformed chart quote data") from exc
        if any(value is None for value in values.values()):
            continue
        bars.append(
            OHLCVBar(
                date=datetime.fromtimestamp(timestamp, timezone.utc).date(),
                open=float(values["open"]),
                high=float(values["high"]),
                low=float(values["low"]),
                close=float(values["close"]),
                volume=float(values["volume"]),
            )
        )
    return bars


def _download_stooq(symbol: str, start: date, end: date) -> list[OHLCVBar]:
    ticker = f"{symbol.lower()}.us"
    url = (
        f"https://stooq.com/q/d/l/?s={ticker}&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d"
    )
    return _parse_provider_csv(_read_url(url))


def _read_url(url: str) -> str:
    with urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def _load_local_csv(path: Path) -> list[OHLCVBar]:
    if not path.exists():
        return []
    return _parse_provider_csv(path.read_text(encoding="utf-8-sig"))


def _parse_provider_csv(text: str) -> list[OHLCVBar]:
    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        return []
    rows: list[OHLCVBar] = []
    for row in reader:
        normalized = {key.strip().lower(): value for key, value in row.items() if key is not None}
        if _is_null_row(normalized):
            continue
        rows.append(
            OHLCVBar(
                date=date.fromisoformat(normalized["date"].strip()),
                open=float(normalized["open"]),
                high=float(normalized["high"]),
                low=float(normalized["low"]),
                close=float(normalized["close"]),
                volume=float(normalized["volume"]),
            )
        )
    return rows


def _is_null_row(row: dict[str, str]) -> bool:
    required = set(REQUIRED_COLUMNS)
    if not required.issubset(row):
        raise ValueError(f"missing columns: {', '.join(column for column in REQUIRED_COLUMNS if column not in row)}")
    return any(row[column] is None or row[column].strip().lower() in {"", "null"} for column in REQUIRED_COLUMNS)


def _bars_by_date(bars: list[OHLCVBar]) -> dict[date, OHLCVBar]:
    return {bar.date: bar for bar in bars}


def _summary(
    symbol: str,
    bars: tuple[OHLCVBar, ...],
    *,
    updated: bool,
    source: str | None,
    error: str | None,
) -> DownloadSummary:
    return DownloadSummary(
        symbol=symbol,
        rows=len(bars),
        start_date=bars[0].date if bars else None,
        end_date=bars[-1].date if bars else None,
        updated=updated,
        source=source,
        error=error,
    )


def _write_csv(path: Path, bars: list[OHLCVBar]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "date": bar.date.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": int(bar.volume) if bar.volume.is_integer() else bar.volume,
                }
            )


if __name__ == "__main__":
    main()

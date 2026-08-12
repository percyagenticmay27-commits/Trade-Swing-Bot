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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .data_tools import REQUIRED_COLUMNS, REQUIRED_SYMBOLS, format_validation_summary, validate_data_directory


DEFAULT_MAX_CACHE_AGE_DAYS = 3
HTTP_429_RETRIES = 3
HTTP_429_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
USER_AGENT = "Mozilla/5.0 (compatible; Trade-Swing-Bot/1.0; read-only-market-data)"


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
    data_source: str | None = None
    is_stale: bool = False
    retrieved_at_utc: str | None = None


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
    max_cache_age_days: int = DEFAULT_MAX_CACHE_AGE_DAYS,
) -> DownloadRun:
    """Download, merge, write, and validate historical OHLCV CSVs.

    Provider order is fresh local cache -> Yahoo CSV -> Yahoo Chart -> Stooq ->
    optional imported historical CSV -> stale local cache.  Stale cache is
    reported explicitly and preserves provider errors so publication can fail
    closed rather than pretending old evidence is live.
    """
    if years <= 0:
        raise ValueError("years must be positive")
    if max_cache_age_days < 0:
        raise ValueError("max_cache_age_days cannot be negative")
    data_dir.mkdir(parents=True, exist_ok=True)

    end = date.today()
    start = end - timedelta(days=round(years * 365.25))
    summaries = tuple(
        _update_symbol(
            symbol,
            data_dir,
            start=start,
            end=end,
            refresh=refresh,
            import_dir=import_dir,
            max_cache_age_days=max_cache_age_days,
        )
        for symbol in symbols
    )
    validations = validate_data_directory(data_dir, as_of=end)
    return DownloadRun(
        summaries=summaries,
        validation_summary=format_validation_summary(validations),
        validation_ok=all(result.is_valid for result in validations),
    )


def format_download_summary(summaries: tuple[DownloadSummary, ...]) -> str:
    """Render the acquisition summary table."""
    lines = [
        "Symbol  Rows  Start Date  End Date    Updated  Source  Stale  Error",
        "------  ----  ----------  ----------  -------  ------  -----  -----",
    ]
    for summary in summaries:
        start = summary.start_date.isoformat() if summary.start_date else "-"
        end = summary.end_date.isoformat() if summary.end_date else "-"
        updated = "yes" if summary.updated else "no"
        source = summary.source or "-"
        stale = "yes" if summary.is_stale else "no"
        error = summary.error or "-"
        lines.append(
            f"{summary.symbol.ljust(6)}  {str(summary.rows).rjust(4)}  {start.ljust(10)}  "
            f"{end.ljust(10)}  {updated.ljust(7)}  {source.ljust(12)}  {stale.ljust(5)}  {error}"
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
    max_cache_age_days: int,
) -> DownloadSummary:
    path = data_dir / f"{symbol}.csv"
    existing = {} if refresh else _bars_by_date(_load_local_csv(path))
    retrieved_at = _utc_now()

    if existing and not refresh:
        local = tuple(sorted(existing.values(), key=lambda bar: bar.date))
        if _cache_is_fresh(local[-1].date, as_of=end, max_age_days=max_cache_age_days):
            return _summary(
                symbol,
                local,
                updated=False,
                source="cache_fresh",
                data_source="CACHE_FRESH",
                is_stale=False,
                retrieved_at_utc=retrieved_at,
                error=None,
            )

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
            source = "historical_csv"
        else:
            errors.append("historical_csv: no rows")

    if not downloaded:
        current = tuple(sorted(existing.values(), key=lambda bar: bar.date))
        return _summary(
            symbol,
            current,
            updated=False,
            source="cache_stale" if current else None,
            data_source="CACHE_STALE_FALLBACK" if current else "UNAVAILABLE",
            is_stale=bool(current),
            retrieved_at_utc=retrieved_at,
            error="; ".join(errors),
        )

    merged = existing
    before = set(merged)
    merged.update(_bars_by_date(downloaded))
    bars = sorted(merged.values(), key=lambda bar: bar.date)
    _write_csv(path, bars)
    updated = bool(set(merged) - before) or refresh
    return _summary(
        symbol,
        tuple(bars),
        updated=updated,
        source=source,
        data_source="LIVE_PROVIDER" if source != "historical_csv" else "HISTORICAL_CSV_FALLBACK",
        is_stale=False,
        retrieved_at_utc=retrieved_at,
        error=None,
    )


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
    # Stooq's downloadable U.S. daily endpoint uses the verified SYMBOL.US form.
    ticker = f"{symbol.lower()}.us"
    url = f"https://stooq.com/q/d/l/?s={ticker}&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d"
    return _parse_provider_csv(_read_url(url))


def _read_url(url: str) -> str:
    """Read a public, read-only market-data URL with bounded 429 backoff."""
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/json,*/*"})
    attempts = HTTP_429_RETRIES + 1
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8-sig")
        except HTTPError as exc:
            if exc.code != 429 or attempt >= HTTP_429_RETRIES:
                raise
            time.sleep(HTTP_429_BACKOFF_SECONDS[attempt])
    raise RuntimeError("unreachable market-data retry state")


def _cache_is_fresh(last_date: date, *, as_of: date, max_age_days: int) -> bool:
    return 0 <= (as_of - last_date).days <= max_age_days


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    data_source: str | None = None,
    is_stale: bool = False,
    retrieved_at_utc: str | None = None,
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
        data_source=data_source,
        is_stale=is_stale,
        retrieved_at_utc=retrieved_at_utc,
    )


def _write_csv(path: Path, bars: list[OHLCVBar]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as output:
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
    temp.replace(path)


if __name__ == "__main__":
    main()

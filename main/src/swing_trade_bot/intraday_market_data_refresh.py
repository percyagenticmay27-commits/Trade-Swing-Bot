"""Swing-owned paper-only intraday archive refresh for frozen strategy engines.

This module keeps timestamped 1-minute NY regular-session OHLCV history separate
from the existing daily market-data pipeline. Recent provider rows are merged into
an append-preserving local archive so older valid intraday history is never lost
when the provider's rolling window moves forward. Both signal symbols and traded
vehicle symbols referenced by frozen specs are refreshed.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, load_frozen_symbol_stacks
from .intraday_chart_bars import IntradayBar, NY_TZ, load_intraday_csv, regular_session_rows

STRATEGY_ID = "SWING-001"
SCHEMA_VERSION = "1.1"
PROVIDER = "YFINANCE"
INTERVAL = "1m"
DEFAULT_PERIOD = "7d"
DEFAULT_DATA_DIR = Path("data/intraday")
DEFAULT_STATUS_PATH = Path("results/intraday_market_data_refresh_status.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
ROBINHOOD_MARKET_DATA_ENABLED = False

FetchRecentBars = Callable[[str], Sequence[IntradayBar]]


@dataclass(frozen=True, slots=True)
class IntradayRefreshSymbolResult:
    symbol: str
    status: str
    fetched_rows: int
    existing_rows: int
    archived_rows: int
    first_timestamp: str | None
    last_timestamp: str | None
    session_row_counts: Mapping[str, int]
    warning: str | None = None
    error: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: Mapping[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return path


def _atomic_csv(path: Path, rows: Sequence[IntradayBar]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "timestamp": row.timestamp.astimezone(NY_TZ).isoformat(),
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                })
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return path


def _session_counts(rows: Iterable[IntradayBar]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = row.timestamp.astimezone(NY_TZ).date().isoformat()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _normalize_frame_rows(frame: object, symbol: str) -> tuple[IntradayBar, ...]:
    if frame is None or getattr(frame, "empty", True):
        raise ValueError(f"YFINANCE returned no 1-minute bars for {symbol}")
    rows: list[IntradayBar] = []
    for index, raw in frame.iterrows():  # type: ignore[attr-defined]
        stamp = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
        if not isinstance(stamp, datetime):
            raise ValueError(f"YFINANCE returned invalid timestamp for {symbol}: {index!r}")
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            stamp = stamp.replace(tzinfo=NY_TZ)
        stamp = stamp.astimezone(NY_TZ)
        rows.append(IntradayBar(
            timestamp=stamp,
            open=float(raw.get("Open")),
            high=float(raw.get("High")),
            low=float(raw.get("Low")),
            close=float(raw.get("Close")),
            volume=float(raw.get("Volume", 0.0)),
        ))
    rows.sort(key=lambda item: item.timestamp)
    if any(current.timestamp <= previous.timestamp for previous, current in zip(rows, rows[1:])):
        raise ValueError(f"YFINANCE returned duplicate/non-increasing timestamps for {symbol}")
    return tuple(regular_session_rows(rows))


def fetch_yfinance_recent_1m(symbol: str, *, period: str = DEFAULT_PERIOD) -> tuple[IntradayBar, ...]:
    """Fetch recent 1-minute rows only; archive retention is handled locally."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is required for intraday refresh") from exc
    try:
        frame = yf.Ticker(symbol).history(
            period=period,
            interval=INTERVAL,
            auto_adjust=False,
            actions=False,
            prepost=False,
            repair=True,
        )
    except Exception as exc:
        raise RuntimeError(f"YFINANCE 1-minute fetch failed for {symbol}: {exc}") from exc
    return _normalize_frame_rows(frame, symbol)


def merge_intraday_archive(existing: Sequence[IntradayBar], recent: Sequence[IntradayBar]) -> tuple[IntradayBar, ...]:
    """Merge by timestamp, letting freshly fetched rows replace overlapping rows."""
    merged = {row.timestamp.astimezone(NY_TZ): row for row in existing}
    for row in recent:
        merged[row.timestamp.astimezone(NY_TZ)] = row
    rows = sorted(merged.values(), key=lambda item: item.timestamp)
    if any(current.timestamp <= previous.timestamp for previous, current in zip(rows, rows[1:])):
        raise ValueError("merged intraday archive timestamps must be unique and strictly increasing")
    return tuple(rows)


def refresh_intraday_market_data(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    data_dir: Path = DEFAULT_DATA_DIR,
    status_path: Path = DEFAULT_STATUS_PATH,
    fetch_recent: FetchRecentBars | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    """Refresh every frozen signal and vehicle symbol and preserve local history."""
    fetcher = fetch_recent or fetch_yfinance_recent_1m
    stacks = load_frozen_symbol_stacks(config_path)
    symbols = sorted({
        symbol
        for stack in stacks
        for spec in (stack.primary, *stack.shadows)
        for symbol in (spec.signal_symbol, spec.vehicle_symbol)
    })
    results: list[IntradayRefreshSymbolResult] = []

    for symbol in symbols:
        target = data_dir / f"{symbol}.csv"
        try:
            existing = tuple(load_intraday_csv(target)) if target.is_file() else ()
            recent = tuple(regular_session_rows(fetcher(symbol)))
            if not recent:
                raise ValueError(f"provider returned no NY regular-session rows for {symbol}")
            merged = merge_intraday_archive(existing, recent)
            _atomic_csv(target, merged)
            counts = _session_counts(merged)
            incomplete = [day for day, count in counts.items() if count < 390]
            warning = None
            if incomplete:
                warning = "Archive contains one or more sessions with fewer than 390 minute rows; partial current sessions, early closes, or provider gaps require review before authoritative stop replay."
            results.append(IntradayRefreshSymbolResult(
                symbol=symbol,
                status="AVAILABLE",
                fetched_rows=len(recent),
                existing_rows=len(existing),
                archived_rows=len(merged),
                first_timestamp=merged[0].timestamp.astimezone(NY_TZ).isoformat(),
                last_timestamp=merged[-1].timestamp.astimezone(NY_TZ).isoformat(),
                session_row_counts=counts,
                warning=warning,
            ))
        except Exception as exc:
            existing_rows = 0
            if target.is_file():
                try:
                    existing_rows = len(load_intraday_csv(target))
                except Exception:
                    pass
            results.append(IntradayRefreshSymbolResult(
                symbol=symbol,
                status="BLOCKED",
                fetched_rows=0,
                existing_rows=existing_rows,
                archived_rows=existing_rows,
                first_timestamp=None,
                last_timestamp=None,
                session_row_counts={},
                error=f"{type(exc).__name__}: {exc}",
            ))

    overall = "AVAILABLE" if results and all(row.status == "AVAILABLE" for row in results) else "BLOCKED"
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "provider": PROVIDER,
        "interval": INTERVAL,
        "data_root": str(data_dir),
        "status": overall,
        "symbols": [asdict(row) for row in results],
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "robinhood_market_data_enabled": False,
    }
    _atomic_json(status_path, payload)
    return payload

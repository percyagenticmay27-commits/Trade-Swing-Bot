"""NY regular-session intraday chart-bar construction for frozen stock research.

The frozen AI-Suggestions stock strategies require session-anchored 1H/4H bars.
This module is research/paper-only and intentionally does not expose execution,
order-placement, brokerage, or capital-movement authority.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Literal
from zoneinfo import ZoneInfo

ChartTimeframe = Literal["1H", "4H", "1D"]
NY_TZ = ZoneInfo("America/New_York")
SESSION_START = time(9, 30)
SESSION_END = time(15, 59, 59, 999999)
SUPPORTED_TIMEFRAMES = {"1H", "4H", "1D"}

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


@dataclass(frozen=True, slots=True)
class IntradayBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close) or self.high < self.low:
            raise ValueError("invalid OHLC range")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")

    @property
    def date(self):
        return self.timestamp.astimezone(NY_TZ).date()

    @property
    def open_price(self) -> float:
        return self.open

    @property
    def high_price(self) -> float:
        return self.high

    @property
    def low_price(self) -> float:
        return self.low


_TIMESTAMP_HEADERS = ("timestamp", "datetime", "date_time", "date time", "time")


def _normalize_header(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def _parse_timestamp(raw: str, *, source_timezone: ZoneInfo) -> datetime:
    text = raw.strip()
    if not text:
        raise ValueError("timestamp is required")
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"unsupported timestamp format: {raw!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=source_timezone)
    return parsed.astimezone(NY_TZ)


def load_intraday_csv(path: Path, *, source_timezone: str = "America/New_York") -> list[IntradayBar]:
    """Load chronological timestamped OHLCV rows and normalize them to New York time."""
    zone = ZoneInfo(source_timezone)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} must contain CSV headers")
        normalized = {_normalize_header(name): name for name in reader.fieldnames}
        timestamp_key = next((normalized.get(_normalize_header(name)) for name in _TIMESTAMP_HEADERS if normalized.get(_normalize_header(name))), None)
        required = {"open", "high", "low", "close", "volume"}
        if timestamp_key is None or not required.issubset(normalized):
            raise ValueError(f"{path} must contain Timestamp/Datetime, Open, High, Low, Close, and Volume columns")
        rows: list[IntradayBar] = []
        for row in reader:
            timestamp = _parse_timestamp(str(row[timestamp_key]), source_timezone=zone)
            rows.append(
                IntradayBar(
                    timestamp=timestamp,
                    open=float(row[normalized["open"]]),
                    high=float(row[normalized["high"]]),
                    low=float(row[normalized["low"]]),
                    close=float(row[normalized["close"]]),
                    volume=float(row[normalized["volume"]]),
                )
            )
    rows.sort(key=lambda bar: bar.timestamp)
    if any(current.timestamp <= previous.timestamp for previous, current in zip(rows, rows[1:])):
        raise ValueError("intraday timestamps must be unique and strictly increasing")
    return rows


def regular_session_rows(rows: Iterable[IntradayBar]) -> list[IntradayBar]:
    """Keep only NY regular-session rows, 09:30 through 15:59:59 ET."""
    output: list[IntradayBar] = []
    for bar in rows:
        local = bar.timestamp.astimezone(NY_TZ)
        if SESSION_START <= local.time() <= SESSION_END:
            output.append(bar)
    return output


def _session_anchor(timestamp: datetime) -> datetime:
    local = timestamp.astimezone(NY_TZ)
    return datetime.combine(local.date(), SESSION_START, tzinfo=NY_TZ)


def _bucket_start(timestamp: datetime, timeframe: ChartTimeframe) -> datetime:
    anchor = _session_anchor(timestamp)
    elapsed_minutes = int((timestamp.astimezone(NY_TZ) - anchor).total_seconds() // 60)
    if timeframe == "1H":
        return anchor + timedelta(minutes=(elapsed_minutes // 60) * 60)
    if timeframe == "4H":
        return anchor if elapsed_minutes < 240 else anchor + timedelta(minutes=240)
    if timeframe == "1D":
        return anchor
    raise ValueError(f"unsupported chart timeframe: {timeframe}")


def build_chart_bars(rows: Iterable[IntradayBar], timeframe: ChartTimeframe) -> list[IntradayBar]:
    """Aggregate NY RTH rows into the frozen 1H/4H/Daily session buckets.

    1H: 09:30, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30 partial.
    4H: 09:30-13:29 and 13:30-15:59 partial.
    1D: one completed 09:30-15:59 RTH bar.
    """
    tf = timeframe.upper()
    if tf not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"unsupported chart timeframe: {timeframe}")
    session_rows = regular_session_rows(rows)
    groups: dict[datetime, list[IntradayBar]] = {}
    for row in session_rows:
        start = _bucket_start(row.timestamp, tf)  # type: ignore[arg-type]
        groups.setdefault(start, []).append(row)

    output: list[IntradayBar] = []
    for start in sorted(groups):
        bucket = groups[start]
        output.append(
            IntradayBar(
                timestamp=start,
                open=bucket[0].open,
                high=max(item.high for item in bucket),
                low=min(item.low for item in bucket),
                close=bucket[-1].close,
                volume=sum(item.volume for item in bucket),
            )
        )
    return output

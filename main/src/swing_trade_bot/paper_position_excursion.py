"""Authoritative paper-position excursion analytics from completed daily bars.

This module is read-only with respect to trading state. It calculates long-position
maximum drawdown only when market-data history covers the paper entry date. It
never infers drawdown from a current snapshot, connects to a broker, places an
order, or moves capital.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False

EXCURSION_SOURCE = "COMPLETED_DAILY_MARK_TO_MARKET_BARS_SINCE_ENTRY"


@dataclass(frozen=True, slots=True)
class PositionExcursionEvidence:
    max_drawdown_amount: float
    max_drawdown_percent: float
    max_drawdown_peak_price: float
    max_drawdown_peak_date: str
    max_drawdown_trough_price: float
    max_drawdown_trough_date: str
    observation_count: int
    source: str = EXCURSION_SOURCE


def calculate_long_position_excursion(
    *,
    market_data_path: Path,
    entry_date: date,
    as_of: date,
    normalized_entry_price: float,
    normalized_shares: float,
) -> PositionExcursionEvidence | None:
    """Return peak-to-trough drawdown evidence for a long paper position.

    The calculation uses completed daily bars through ``as_of`` plus the actual
    normalized paper entry price as the initial observation. A bar at or before
    the entry date is required to prove that the available history covers the
    position lifetime. If that coverage is unavailable, ``None`` is returned so
    callers cannot understate drawdown from a truncated history window.
    """
    if as_of < entry_date:
        raise ValueError("as_of cannot precede entry_date")
    entry_price = _positive(normalized_entry_price, "normalized_entry_price")
    shares = _positive(normalized_shares, "normalized_shares")
    bars = _completed_mark_prices(market_data_path, as_of)
    if not bars:
        return None
    if not any(day <= entry_date for day, _ in bars):
        return None

    observations: list[tuple[date, float]] = [(entry_date, entry_price)]
    observations.extend((day, price) for day, price in bars if day >= entry_date)

    peak_date = entry_date
    peak_price = entry_price
    worst_peak_date = entry_date
    worst_peak_price = entry_price
    worst_trough_date = entry_date
    worst_trough_price = entry_price
    max_drawdown_per_share = 0.0

    for day, price in observations[1:]:
        if price > peak_price:
            peak_price = price
            peak_date = day
            continue
        drawdown = peak_price - price
        if drawdown > max_drawdown_per_share:
            max_drawdown_per_share = drawdown
            worst_peak_price = peak_price
            worst_peak_date = peak_date
            worst_trough_price = price
            worst_trough_date = day

    percent = (
        (max_drawdown_per_share / worst_peak_price) * 100.0
        if worst_peak_price > 0
        else 0.0
    )
    return PositionExcursionEvidence(
        max_drawdown_amount=round(max_drawdown_per_share * shares, 2),
        max_drawdown_percent=round(percent, 6),
        max_drawdown_peak_price=round(worst_peak_price, 12),
        max_drawdown_peak_date=worst_peak_date.isoformat(),
        max_drawdown_trough_price=round(worst_trough_price, 12),
        max_drawdown_trough_date=worst_trough_date.isoformat(),
        observation_count=len(observations),
    )


def calculate_closed_long_trade_excursion(
    *,
    market_data_path: Path,
    entry_date: date,
    exit_date: date,
    entry_price: float,
    shares: float,
) -> PositionExcursionEvidence | None:
    """Return lifetime drawdown for a completed long paper trade.

    Raw FIFO trade history retains the execution-time share count and entry
    price. When adjusted-close history proves a simple split at entry, normalize
    those values before reusing the authoritative position excursion engine.
    Unsupported adjustment ratios fail closed instead of fabricating drawdown.
    """
    if exit_date < entry_date:
        raise ValueError("exit_date cannot precede entry_date")
    raw_entry = _positive(entry_price, "entry_price")
    raw_shares = _positive(shares, "shares")
    factor = _entry_split_factor(market_data_path, entry_date)
    if factor is None:
        return None
    return calculate_long_position_excursion(
        market_data_path=market_data_path,
        entry_date=entry_date,
        as_of=exit_date,
        normalized_entry_price=raw_entry / factor,
        normalized_shares=raw_shares * factor,
    )


def _entry_split_factor(path: Path, entry_date: date) -> float | None:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError(f"market data has no headers: {path}")
        names = {name.strip().lower().replace("_", " "): name for name in reader.fieldnames}
        if "date" not in names or "close" not in names:
            raise ValueError(f"market data must contain Date and Close: {path}")
        adj_name = names.get("adj close")
        candidates: list[tuple[date, float, float | None]] = []
        for row in reader:
            day = date.fromisoformat(str(row[names["date"]]).strip()[:10])
            if day > entry_date:
                continue
            close = _positive(row[names["close"]], f"{path.name}.{day}.Close")
            adjusted = None
            if adj_name and str(row.get(adj_name, "")).strip() != "":
                adjusted = _positive(row[adj_name], f"{path.name}.{day}.Adj Close")
            candidates.append((day, close, adjusted))
    if not candidates:
        return None
    _, close, adjusted = max(candidates, key=lambda item: item[0])
    if adjusted is None:
        return 1.0
    ratio = close / adjusted
    nearest = round(ratio)
    if math.isclose(ratio, 1.0, rel_tol=0.0, abs_tol=0.02):
        return 1.0
    if nearest >= 1 and math.isclose(ratio, nearest, rel_tol=0.0, abs_tol=0.02):
        return float(nearest)
    return None


def _completed_mark_prices(path: Path, as_of: date) -> list[tuple[date, float]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError(f"market data has no headers: {path}")
        names = {name.strip().lower().replace("_", " "): name for name in reader.fieldnames}
        if "date" not in names or "close" not in names:
            raise ValueError(f"market data must contain Date and Close: {path}")
        adj_name = names.get("adj close")
        seen: dict[date, float] = {}
        for row in reader:
            day = date.fromisoformat(str(row[names["date"]]).strip()[:10])
            if day > as_of:
                continue
            close = _positive(row[names["close"]], f"{path.name}.{day}.Close")
            price = close
            if adj_name and str(row.get(adj_name, "")).strip() != "":
                price = _positive(row[adj_name], f"{path.name}.{day}.Adj Close")
            if day in seen and not math.isclose(seen[day], price, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(f"conflicting duplicate market-data date: {path}:{day}")
            seen[day] = price
    return [(day, round(price, 12)) for day, price in sorted(seen.items())]


def _positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return number

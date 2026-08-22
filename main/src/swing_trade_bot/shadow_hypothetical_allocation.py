"""Resolve the dollar allocation a shadow symbol would receive if activated now.

This module reuses the authoritative PortfolioAllocationEngine. It never writes the
portfolio allocation artifact, reserves capital, moves SGOV, or creates a position.
Existing funded symbols use their exact current allocation percentage. An unfunded
WATCHLIST candidate is modeled at the established first funded lifecycle tier, LOW,
and the current live candidate set is reallocated only in memory.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .portfolio_allocation_engine import (
    CASH_EQUIVALENT_SYMBOL,
    PortfolioAllocationEngine,
    PortfolioCandidate,
)

DEFAULT_PORTFOLIO_ALLOCATIONS_PATH = Path("results/portfolio_allocations.json")
DEFAULT_WATCHLIST_PATH = Path("results/watchlist_report.json")
DEFAULT_PAPER_PORTFOLIO_SUMMARY_PATH = Path("results/paper_ledger/paper_portfolio_summary.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
CAPITAL_RESERVATION_ENABLED = False
PORTFOLIO_ALLOCATION_WRITE_ENABLED = False
FIRST_FUNDED_LIFECYCLE_LEVEL = "LOW"


@dataclass(frozen=True, slots=True)
class ShadowAllocationResolution:
    underlying_symbol: str
    vehicle_symbol: str
    allocation_percent: float
    simulated_allocation: float
    allocation_source: str
    account_capital: float
    activation_level: str
    capital_reserved: bool = False
    paper_trade_mode: bool = True


def _load(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _account_capital(path: Path) -> float:
    payload = _load(path)
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("paper portfolio summary must preserve paper_trade_mode=True")
    value = payload.get("account_capital")
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("paper portfolio summary account_capital must be numeric") from exc
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("paper portfolio summary account_capital must be positive")
    return amount


def _watchlist_row(path: Path, underlying_symbol: str) -> Mapping[str, Any]:
    payload = _load(path)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("watchlist report must contain rows")
    target = underlying_symbol.strip().upper()
    for row in rows:
        if isinstance(row, Mapping) and str(row.get("underlying_symbol", "")).strip().upper() == target:
            return row
    raise ValueError(f"watchlist row not found for {target}")


def _rank(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = int(float(str(value)))
    return parsed if parsed > 0 else None


def _live_candidates(payload: Mapping[str, Any], *, exclude_symbol: str) -> list[PortfolioCandidate]:
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("portfolio allocations must preserve paper_trade_mode=True")
    rows = payload.get("allocations")
    if not isinstance(rows, list):
        raise ValueError("portfolio allocations must contain allocations")
    excluded = exclude_symbol.upper()
    candidates: list[PortfolioCandidate] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol or symbol in {excluded, CASH_EQUIVALENT_SYMBOL}:
            continue
        level = str(row.get("confidence_level", "")).strip().upper()
        if level not in {"LOW", "MEDIUM", "HIGH"}:
            continue
        candidates.append(
            PortfolioCandidate(
                symbol=symbol,
                confidence_level=level,
                active_strategy=str(row.get("active_strategy", "Strategy A")),
                rank=_rank(row.get("rank")),
                theme=str(row.get("theme", "Unclassified")) or "Unclassified",
            )
        )
    return candidates


def resolve_shadow_allocation(
    *,
    underlying_symbol: str,
    vehicle_symbol: str,
    portfolio_allocations_path: Path = DEFAULT_PORTFOLIO_ALLOCATIONS_PATH,
    watchlist_path: Path = DEFAULT_WATCHLIST_PATH,
    paper_portfolio_summary_path: Path = DEFAULT_PAPER_PORTFOLIO_SUMMARY_PATH,
) -> ShadowAllocationResolution:
    """Return current or hypothetical dollar allocation without reserving capital."""
    underlying = underlying_symbol.strip().upper()
    vehicle = vehicle_symbol.strip().upper()
    if not underlying or not vehicle:
        raise ValueError("underlying_symbol and vehicle_symbol are required")

    allocations = _load(portfolio_allocations_path)
    capital = _account_capital(paper_portfolio_summary_path)
    rows = allocations.get("allocations")
    if not isinstance(rows, list):
        raise ValueError("portfolio allocations must contain allocations")

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("symbol", "")).strip().upper() != vehicle:
            continue
        level = str(row.get("confidence_level", "")).strip().upper()
        if level == "RESERVE":
            continue
        percent = float(row.get("allocation_percent", 0.0))
        if not math.isfinite(percent) or percent <= 0:
            break
        return ShadowAllocationResolution(
            underlying_symbol=underlying,
            vehicle_symbol=vehicle,
            allocation_percent=round(percent, 6),
            simulated_allocation=round(capital * percent / 100.0, 2),
            allocation_source="CURRENT_FUNDED_SWING_ALLOCATION",
            account_capital=round(capital, 2),
            activation_level=level or "CURRENT",
        )

    watchlist = _watchlist_row(watchlist_path, underlying)
    rank = _rank(watchlist.get("watchlist_rank") or watchlist.get("high_priority_rank"))
    themes = str(watchlist.get("themes", ""))
    theme = next((item.strip() for item in themes.replace("|", ";").split(";") if item.strip()), "Unclassified")

    candidates = _live_candidates(allocations, exclude_symbol=vehicle)
    candidates.append(
        PortfolioCandidate(
            symbol=vehicle,
            confidence_level=FIRST_FUNDED_LIFECYCLE_LEVEL,
            active_strategy="MANUAL_DIRECT_OR_SHADOW",
            rank=rank,
            theme=theme,
        )
    )
    report = PortfolioAllocationEngine(paper_trade_mode=True).allocate(candidates)
    target = next((row for row in report.rows if row.symbol == vehicle), None)
    if target is None or target.allocation_percent <= 0:
        raise ValueError(f"allocator produced no funded allocation for {vehicle}")

    percent = target.allocation_percent
    return ShadowAllocationResolution(
        underlying_symbol=underlying,
        vehicle_symbol=vehicle,
        allocation_percent=round(percent, 6),
        simulated_allocation=round(capital * percent / 100.0, 2),
        allocation_source="HYPOTHETICAL_CURRENT_SWING_POLICY_LOW_ACTIVATION",
        account_capital=round(capital, 2),
        activation_level=FIRST_FUNDED_LIFECYCLE_LEVEL,
    )

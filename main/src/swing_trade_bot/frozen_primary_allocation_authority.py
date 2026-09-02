"""Resolve paper-only dollar authority for a new frozen DIRECT Primary entry.

The AI CIO owns the SWING-001 strategy-level capital allocation. The Swing
portfolio allocator owns security-level allocation percentages. This module
combines those two existing authorities without inventing dollars, moving
capital, creating positions, or placing orders.

Frozen mappings are resolved by ``signal_symbol`` first because portfolio
allocation rows are produced from underlying/watchlist symbols. ``vehicle_symbol``
is accepted only as an unambiguous fallback for same-symbol or vehicle-keyed
legacy rows. Missing or zero security allocation fails closed.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .enterprise_strategy_allocation_discovery import (
    DEFAULT_AI_CIO_KPI_RELATIVE_PATH,
    DEFAULT_AI_CIO_REGISTRY_RELATIVE_PATH,
    DEFAULT_AI_CIO_REPOSITORY,
    STRATEGY_ID,
    load_discovered_strategy_allocations,
    resolve_strategy_allocation_evidence,
)

DEFAULT_PORTFOLIO_ALLOCATION_PATH = Path("results/portfolio_allocations.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


@dataclass(frozen=True, slots=True)
class FrozenPrimaryAllocationAuthority:
    signal_symbol: str
    vehicle_symbol: str
    allocation_symbol: str
    allocation_percent: float
    strategy_allocated_capital: float
    authorized_notional: float
    portfolio_allocation_path: str
    strategy_allocation_source_path: str
    strategy_allocation_source_json_path: str
    strategy_allocation_field: str
    paper_trade_mode: bool = True
    live_trading_enabled: bool = False
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    capital_movement_enabled: bool = False

    def __post_init__(self) -> None:
        for field_name in ("signal_symbol", "vehicle_symbol", "allocation_symbol"):
            value = getattr(self, field_name)
            if not value or value != value.strip().upper():
                raise ValueError(f"{field_name} must be uppercase and trimmed")
        if not math.isfinite(self.allocation_percent) or not 0 < self.allocation_percent <= 100:
            raise ValueError("allocation_percent must be finite and within (0, 100]")
        if not math.isfinite(self.strategy_allocated_capital) or self.strategy_allocated_capital <= 0:
            raise ValueError("strategy_allocated_capital must be positive and finite")
        if not math.isfinite(self.authorized_notional) or self.authorized_notional <= 0:
            raise ValueError("authorized_notional must be positive and finite")
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if any((self.live_trading_enabled, self.broker_execution_enabled,
                self.order_placement_enabled, self.capital_movement_enabled)):
            raise ValueError("frozen Primary allocation authority is paper-only")

    def row(self) -> dict[str, Any]:
        return asdict(self)


def resolve_frozen_primary_allocation_authority(
    *,
    signal_symbol: str,
    vehicle_symbol: str,
    portfolio_allocation_path: Path = DEFAULT_PORTFOLIO_ALLOCATION_PATH,
    strategy_allocation_path: Path | None = None,
    ai_cio_repository: Path = DEFAULT_AI_CIO_REPOSITORY,
    registry_relative_path: Path = DEFAULT_AI_CIO_REGISTRY_RELATIVE_PATH,
    kpi_relative_path: Path = DEFAULT_AI_CIO_KPI_RELATIVE_PATH,
) -> FrozenPrimaryAllocationAuthority | None:
    """Return authorized paper notional, or ``None`` when no security allocation exists.

    The dollar value is exactly::

        SWING-001 allocated capital * security allocation percent / 100

    No default position size is used. A missing/zero local security allocation
    therefore leaves a new frozen Primary flat.
    """
    signal = _symbol(signal_symbol, "signal_symbol")
    vehicle = _symbol(vehicle_symbol, "vehicle_symbol")
    portfolio_path = Path(portfolio_allocation_path)
    if not portfolio_path.is_file():
        return None

    portfolio = _load_json_object(portfolio_path)
    if portfolio.get("paper_trade_mode") is not True:
        raise ValueError("portfolio allocation artifact must be paper_trade_mode=true")
    if portfolio.get("capital_movement_enabled") not in (False, None):
        raise ValueError("portfolio allocation artifact cannot enable capital movement")
    rows = portfolio.get("allocations")
    if not isinstance(rows, list):
        raise ValueError("portfolio allocation artifact must contain allocations list")

    matches: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("portfolio allocation rows must be objects")
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol in {signal, vehicle}:
            if symbol in matches:
                raise ValueError(f"duplicate portfolio allocation row for {symbol}")
            matches[symbol] = row

    # Underlying/signal authority is preferred because the portfolio allocator is
    # fed by watchlist underlying symbols. Vehicle is a legacy/same-symbol fallback.
    allocation_symbol = signal if signal in matches else vehicle if vehicle in matches else ""
    if not allocation_symbol:
        return None
    allocation_percent = _finite(matches[allocation_symbol].get("allocation_percent"), "allocation_percent")
    if allocation_percent <= 0:
        return None
    if allocation_percent > 100:
        raise ValueError("allocation_percent cannot exceed 100")

    payload, source = load_discovered_strategy_allocations(
        strategy_allocation_path,
        ai_cio_repository=ai_cio_repository,
        registry_relative_path=registry_relative_path,
        kpi_relative_path=kpi_relative_path,
    )
    evidence = resolve_strategy_allocation_evidence(
        payload,
        STRATEGY_ID,
        source_path=source,
    )
    strategy_capital = _finite(evidence.get("allocated_capital"), "SWING-001 allocated_capital")
    if strategy_capital <= 0:
        raise ValueError("SWING-001 allocated_capital must be positive")
    authorized = round(strategy_capital * allocation_percent / 100.0, 2)
    if authorized <= 0:
        return None

    return FrozenPrimaryAllocationAuthority(
        signal_symbol=signal,
        vehicle_symbol=vehicle,
        allocation_symbol=allocation_symbol,
        allocation_percent=allocation_percent,
        strategy_allocated_capital=strategy_capital,
        authorized_notional=authorized,
        portfolio_allocation_path=str(portfolio_path.resolve()),
        strategy_allocation_source_path=str(evidence.get("allocation_source_path", source)),
        strategy_allocation_source_json_path=str(evidence.get("allocation_source_json_path", "")),
        strategy_allocation_field=str(evidence.get("allocation_field", "")),
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _symbol(value: str, field: str) -> str:
    normalized = str(value).strip().upper()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _finite(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return number

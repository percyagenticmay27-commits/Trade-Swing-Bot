"""Host-compatible Swing Enterprise KPI facade.

This module delegates to the Swing-owned, paper-only KPI publisher. It does not
import external host production modules, access brokerage execution, move
capital, place orders, or write directly to the AI CIO database.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .enterprise_strategy_kpi_publisher import (
    DEFAULT_STRATEGY_ALLOCATIONS_PATH,
    MODULE_NAME,
    MODULE_VERSION,
    SCHEMA_VERSION,
    STRATEGY_ID,
    build_and_write_enterprise_strategy_kpis,
    build_enterprise_strategy_kpis,
    resolve_strategy_allocation,
    validate_enterprise_strategy_kpis,
    write_enterprise_strategy_kpis,
)

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False


def build_kpis(
    results_dir: str | Path = "results",
    *,
    strategy_allocations: Mapping[str, Any],
    strategy_allocations_source: str | Path | None = None,
) -> dict[str, Any]:
    """Build Swing KPI evidence from existing reports and preserved allocation."""
    return build_enterprise_strategy_kpis(
        results_dir,
        strategy_allocations=strategy_allocations,
        strategy_allocations_source=strategy_allocations_source,
    )


def validate_kpis(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return validate_enterprise_strategy_kpis(payload)


def publish_kpis(
    results_dir: str | Path = "results",
    output_path: str | Path = "results/enterprise_strategy_kpis.json",
    *,
    strategy_allocations_path: str | Path = DEFAULT_STRATEGY_ALLOCATIONS_PATH,
) -> Path:
    """Atomically publish host-readable Swing KPI evidence."""
    return build_and_write_enterprise_strategy_kpis(
        results_dir,
        output_path,
        strategy_allocations_path=strategy_allocations_path,
    )


__all__ = [
    "BROKER_EXECUTION_ENABLED",
    "CAPITAL_MOVEMENT_ENABLED",
    "DEFAULT_STRATEGY_ALLOCATIONS_PATH",
    "DIRECT_DATABASE_WRITES",
    "LIVE_TRADING_ENABLED",
    "MODULE_NAME",
    "MODULE_VERSION",
    "ORDER_PLACEMENT_ENABLED",
    "PAPER_TRADE_MODE",
    "SCHEMA_VERSION",
    "STRATEGY_ID",
    "build_and_write_enterprise_strategy_kpis",
    "build_enterprise_strategy_kpis",
    "build_kpis",
    "publish_kpis",
    "resolve_strategy_allocation",
    "validate_enterprise_strategy_kpis",
    "validate_kpis",
    "write_enterprise_strategy_kpis",
]

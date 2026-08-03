"""Host-compatible Swing Enterprise KPI facade.

This module provides the compact Enterprise KPI entry points expected by the
existing AI CIO host while delegating all calculations and publication to the
Swing-owned, paper-only KPI publisher.

It intentionally does not import Trade-Dividend-Bot production modules, access
brokerage execution, move capital, place orders, or write directly to the AI
CIO database.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .enterprise_strategy_kpi_publisher import (
    DEFAULT_ALLOCATED_CAPITAL,
    MODULE_NAME,
    MODULE_VERSION,
    SCHEMA_VERSION,
    STRATEGY_ID,
    build_and_write_enterprise_strategy_kpis,
    build_enterprise_strategy_kpis,
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
    allocated_capital: float = DEFAULT_ALLOCATED_CAPITAL,
) -> dict[str, Any]:
    """Build read-only Swing KPI evidence from existing Swing report files."""
    return build_enterprise_strategy_kpis(
        results_dir,
        allocated_capital=allocated_capital,
    )


def validate_kpis(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate Swing KPI evidence against locked paper-only requirements."""
    return validate_enterprise_strategy_kpis(payload)


def publish_kpis(
    results_dir: str | Path = "results",
    output_path: str | Path = "results/enterprise_strategy_kpis.json",
    *,
    allocated_capital: float = DEFAULT_ALLOCATED_CAPITAL,
) -> Path:
    """Atomically publish host-readable Swing KPI evidence."""
    return build_and_write_enterprise_strategy_kpis(
        results_dir,
        output_path,
        allocated_capital=allocated_capital,
    )


__all__ = [
    "BROKER_EXECUTION_ENABLED",
    "CAPITAL_MOVEMENT_ENABLED",
    "DEFAULT_ALLOCATED_CAPITAL",
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
    "validate_enterprise_strategy_kpis",
    "validate_kpis",
    "write_enterprise_strategy_kpis",
]

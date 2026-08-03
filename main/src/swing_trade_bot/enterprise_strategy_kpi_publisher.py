"""Publish read-only Swing KPI evidence for the existing Enterprise dashboard.

The publisher reads existing Swing reports only. It never imports host or
Dividend production code, writes to a database, moves capital, or reaches a
broker. When marked-to-market portfolio value is unavailable, it discloses a
paper-allocation proxy rather than pretending the value is live brokerage data.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "enterprise_strategy_kpi_publisher"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
STRATEGY_ID = "SWING-001"
DEFAULT_ALLOCATED_CAPITAL = 10_000.0


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _finite_nonnegative(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _find_numeric(payload: Mapping[str, Any] | None, keys: tuple[str, ...]) -> float | None:
    if not payload:
        return None
    for key in keys:
        value = _finite_nonnegative(payload.get(key))
        if value is not None:
            return value
    for value in payload.values():
        if isinstance(value, Mapping):
            found = _find_numeric(value, keys)
            if found is not None:
                return found
    return None


def _active_positions(allocations: Mapping[str, Any] | None) -> int | None:
    if not allocations:
        return None
    rows = allocations.get("allocations")
    if not isinstance(rows, list):
        return None
    count = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        percent = _finite_nonnegative(row.get("allocation_percent")) or 0.0
        reserve = str(row.get("confidence_level") or "").upper() == "RESERVE"
        cash_equivalent = bool(str(row.get("cash_equivalent") or "").strip())
        if percent > 0 and not reserve and not cash_equivalent:
            count += 1
    return count


def build_enterprise_strategy_kpis(
    results_dir: str | Path = "results",
    *,
    allocated_capital: float = DEFAULT_ALLOCATED_CAPITAL,
) -> dict[str, Any]:
    root = Path(results_dir)
    allocations = _load_json(root / "portfolio_allocations.json")
    executive = _load_json(root / "executive_dashboard.json")
    opportunity = _load_json(root / "opportunity_quality_report.json")
    watchlist = _load_json(root / "watchlist_report.json")

    allocated = _finite_nonnegative(allocated_capital)
    if allocated is None:
        raise ValueError("allocated_capital must be a finite nonnegative number")

    warnings: list[str] = []
    portfolio_value = _find_numeric(
        executive,
        ("portfolio_value", "current_portfolio_value", "total_portfolio_value"),
    )
    portfolio_value_source = "EXECUTIVE_DASHBOARD"
    if portfolio_value is None:
        portfolio_value = allocated
        portfolio_value_source = "PAPER_ALLOCATION_PROXY"
        warnings.append(
            "Marked-to-market portfolio value is unavailable; using allocated paper capital as a disclosed proxy."
        )

    position_count = _active_positions(allocations)
    if position_count is None:
        position_count = int(_find_numeric(executive, ("active_positions", "position_count")) or 0)
        warnings.append("Position count was not available from portfolio_allocations.json.")

    source_artifacts = {
        "portfolio_allocations.json": allocations is not None,
        "executive_dashboard.json": executive is not None,
        "opportunity_quality_report.json": opportunity is not None,
        "watchlist_report.json": watchlist is not None,
    }
    available_count = sum(source_artifacts.values())
    evidence_status = "AVAILABLE" if allocations is not None else "REGISTRY_ONLY"

    return {
        "schema_version": SCHEMA_VERSION,
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "strategy_id": STRATEGY_ID,
        "plugin_id": STRATEGY_ID,
        "strategy_name": "Trade Swing Bot",
        "allocated_capital": round(allocated, 2),
        "portfolio_value": round(portfolio_value, 2),
        "portfolio_value_source": portfolio_value_source,
        "position_count": int(position_count),
        "evidence_status": evidence_status,
        "capabilities": [
            "opportunity_quality",
            "portfolio_allocations",
            "strategy_kpis",
            "watchlist",
        ],
        "artifacts": available_count,
        "source_artifacts": source_artifacts,
        "warnings": warnings,
        "errors": [],
        "paper_trade_mode": True,
        "paper_compatible": True,
        "advisory_only": True,
        "reporting_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "capital_movement_enabled": False,
        "order_placement_enabled": False,
        "automatic_activation_allowed": False,
        "governance_review_required": True,
        "direct_database_writes": False,
    }


def validate_enterprise_strategy_kpis(payload: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if payload.get("strategy_id") != STRATEGY_ID:
        errors.append("strategy_id must be SWING-001")
    if payload.get("evidence_status") not in {"AVAILABLE", "REGISTRY_ONLY"}:
        errors.append("unsupported evidence_status")
    for field in ("allocated_capital", "portfolio_value"):
        if _finite_nonnegative(payload.get(field)) is None:
            errors.append(f"{field} must be finite and nonnegative")
    if not isinstance(payload.get("position_count"), int) or payload.get("position_count", -1) < 0:
        errors.append("position_count must be a nonnegative integer")
    for field in (
        "paper_trade_mode", "paper_compatible", "advisory_only", "reporting_only",
        "governance_review_required",
    ):
        if payload.get(field) is not True:
            errors.append(f"{field} must be true")
    for field in (
        "live_trading_enabled", "broker_execution_enabled", "capital_movement_enabled",
        "order_placement_enabled", "automatic_activation_allowed", "direct_database_writes",
    ):
        if payload.get(field) is not False:
            errors.append(f"{field} must be false")
    return tuple(errors)


def write_enterprise_strategy_kpis(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    errors = validate_enterprise_strategy_kpis(payload)
    if errors:
        raise ValueError("Invalid Swing enterprise KPI evidence: " + "; ".join(errors))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def build_and_write_enterprise_strategy_kpis(
    results_dir: str | Path = "results",
    output_path: str | Path = "results/enterprise_strategy_kpis.json",
    *,
    allocated_capital: float = DEFAULT_ALLOCATED_CAPITAL,
) -> Path:
    payload = build_enterprise_strategy_kpis(results_dir, allocated_capital=allocated_capital)
    return write_enterprise_strategy_kpis(payload, output_path)

"""Research-only Shadow workflow with authoritative hypothetical allocation sizing.

The workflow resolves a simulated dollar allocation for every enabled SHADOW
assignment, writes that evidence to a separate Shadow-only artifact, then invokes
the validated manual strategy shadow runner. It never mutates portfolio_allocations,
reserves capital, moves SGOV, creates paper positions, or promotes strategies.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .manual_entry_strategy_registry import load_manual_entry_strategy_registry
from .manual_strategy_shadow_runner import (
    DEFAULT_ASSIGNMENT_REPORT_PATH,
    DEFAULT_DATA_DIR,
    DEFAULT_LEDGER_PATH,
    DEFAULT_MAPPING_PATH,
    DEFAULT_PERFORMANCE_PATH,
    DEFAULT_REGISTRY_PATH,
    build_and_write_shadow_strategies as run_with_resolved_allocations,
)
from .shadow_hypothetical_allocation import (
    DEFAULT_PAPER_PORTFOLIO_SUMMARY_PATH,
    DEFAULT_PORTFOLIO_ALLOCATIONS_PATH,
    DEFAULT_WATCHLIST_PATH,
    resolve_shadow_allocation,
)

DEFAULT_SHADOW_ALLOCATION_PATH = Path("results/shadow_strategy_allocations.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
CAPITAL_RESERVATION_ENABLED = False
SGOV_MOVEMENT_ENABLED = False
AUTO_PROMOTION_ENABLED = False


def _mapping(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            underlying = str(row.get("underlying_symbol", "")).strip().upper()
            vehicle = str(row.get("leveraged_symbol", "")).strip().upper()
            if underlying and vehicle:
                result[underlying] = vehicle
    return result


def _atomic_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def build_shadow_allocation_evidence(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    mapping_path: Path = DEFAULT_MAPPING_PATH,
    portfolio_allocations_path: Path = DEFAULT_PORTFOLIO_ALLOCATIONS_PATH,
    watchlist_path: Path = DEFAULT_WATCHLIST_PATH,
    paper_portfolio_summary_path: Path = DEFAULT_PAPER_PORTFOLIO_SUMMARY_PATH,
    output_path: Path = DEFAULT_SHADOW_ALLOCATION_PATH,
) -> dict[str, Any]:
    registry = load_manual_entry_strategy_registry(registry_path)
    mappings = _mapping(mapping_path)
    rows: list[dict[str, Any]] = []

    for assignment in registry.assignments:
        if assignment.assignment_mode != "SHADOW" or not assignment.enabled:
            continue
        underlying = assignment.underlying_symbol
        vehicle = mappings.get(underlying)
        base = {
            "underlying_symbol": underlying,
            "strategy_id": assignment.strategy_id,
            "vehicle_symbol": vehicle,
        }
        if not vehicle:
            rows.append({**base, "evidence_status": "MISSING_VERIFIED_MAPPING"})
            continue
        try:
            resolution = resolve_shadow_allocation(
                underlying_symbol=underlying,
                vehicle_symbol=vehicle,
                portfolio_allocations_path=portfolio_allocations_path,
                watchlist_path=watchlist_path,
                paper_portfolio_summary_path=paper_portfolio_summary_path,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            rows.append({
                **base,
                "evidence_status": "MISSING_SWING_ALLOCATION",
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        rows.append({
            **base,
            "evidence_status": "AVAILABLE",
            "allocated_capital": resolution.simulated_allocation,
            "allocation_percent": resolution.allocation_percent,
            "allocation_source": resolution.allocation_source,
            "activation_level": resolution.activation_level,
            "account_capital": resolution.account_capital,
            "capital_reserved": False,
        })

    payload = {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "research_only": True,
        "capital_reserved": False,
        "capital_movement_enabled": False,
        "sgov_movement_enabled": False,
        "portfolio_allocations_modified": False,
        "rows": rows,
    }
    _atomic_json(output_path, payload)
    return payload


def build_and_write_shadow_strategies(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    mapping_path: Path = DEFAULT_MAPPING_PATH,
    data_dir: Path = DEFAULT_DATA_DIR,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    performance_path: Path = DEFAULT_PERFORMANCE_PATH,
    assignment_report_path: Path = DEFAULT_ASSIGNMENT_REPORT_PATH,
    shadow_allocation_path: Path = DEFAULT_SHADOW_ALLOCATION_PATH,
    portfolio_allocations_path: Path = DEFAULT_PORTFOLIO_ALLOCATIONS_PATH,
    watchlist_path: Path = DEFAULT_WATCHLIST_PATH,
    paper_portfolio_summary_path: Path = DEFAULT_PAPER_PORTFOLIO_SUMMARY_PATH,
) -> dict[str, Any]:
    allocation_evidence = build_shadow_allocation_evidence(
        registry_path=registry_path,
        mapping_path=mapping_path,
        portfolio_allocations_path=portfolio_allocations_path,
        watchlist_path=watchlist_path,
        paper_portfolio_summary_path=paper_portfolio_summary_path,
        output_path=shadow_allocation_path,
    )
    result = run_with_resolved_allocations(
        registry_path=registry_path,
        allocation_path=shadow_allocation_path,
        mapping_path=mapping_path,
        data_dir=data_dir,
        ledger_path=ledger_path,
        performance_path=performance_path,
        assignment_report_path=assignment_report_path,
    )
    result["shadow_allocation_evidence_count"] = sum(
        1 for row in allocation_evidence["rows"] if row.get("evidence_status") == "AVAILABLE"
    )
    return result


if __name__ == "__main__":
    result = build_and_write_shadow_strategies()
    available = sum(1 for row in result.get("rows", []) if row.get("evidence_status") == "AVAILABLE")
    print(
        f"Shadow strategy workflow: {len(result.get('rows', []))} shadow assignments; "
        f"{available} with performance evidence"
    )

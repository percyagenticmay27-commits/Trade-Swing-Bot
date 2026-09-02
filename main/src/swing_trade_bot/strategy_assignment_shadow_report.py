"""Host-readable DIRECT/SHADOW strategy assignment report for SWING-001.

The report is descriptive and paper-only. DIRECT identifies the one strategy that
may be resolved for entry authority. SHADOW identifies research-only strategies
that simulate using the current Primary paper-position share quantity without
reserving or moving capital. Current Swing allocation is retained as comparison
normalization context only. Optional shadow performance evidence is joined when
available.

A qualified shadow does not require affirmative user approval. Qualification is
followed by a veto opportunity; absent a veto, the promotion lifecycle may promote
the shadow automatically after its configured deadline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .manual_entry_strategy_registry import load_manual_entry_strategy_registry

DEFAULT_REGISTRY_PATH = Path("configs/manual_entry_strategies.json")
DEFAULT_ALLOCATION_PATH = Path("results/portfolio_allocations.json")
DEFAULT_SHADOW_PERFORMANCE_PATH = Path("results/shadow_strategy_performance.json")
DEFAULT_OUTPUT_PATH = Path("results/strategy_assignment_shadow_report.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
SHADOW_POSITION_CREATION_ENABLED = False
AUTO_PROMOTION_ENABLED = True
AFFIRMATIVE_APPROVAL_REQUIRED = False
USER_VETO_ALLOWED = True


def _load_mapping(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _allocation_by_symbol(payload: Mapping[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    rows = payload.get("allocations")
    if not isinstance(rows, list):
        rows = payload.get("rows")
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("underlying_symbol") or row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        for key in ("allocated_capital", "allocation", "allocation_amount", "dollar_allocation"):
            value = row.get(key)
            if isinstance(value, (int, float)):
                result[symbol] = round(float(value), 2)
                break
    return result


def _shadow_evidence(payload: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = payload.get("strategies")
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("underlying_symbol") or row.get("symbol") or "").strip().upper()
        strategy_id = str(row.get("strategy_id") or "").strip().upper()
        if symbol and strategy_id:
            result[(symbol, strategy_id)] = row
    return result


def build_strategy_assignment_shadow_report(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    allocation_path: Path = DEFAULT_ALLOCATION_PATH,
    shadow_performance_path: Path = DEFAULT_SHADOW_PERFORMANCE_PATH,
) -> dict[str, Any]:
    registry = load_manual_entry_strategy_registry(registry_path)
    by_id = {item.strategy_id: item for item in registry.strategies}
    allocations = _allocation_by_symbol(_load_mapping(allocation_path))
    evidence = _shadow_evidence(_load_mapping(shadow_performance_path))

    symbols = sorted({item.underlying_symbol for item in registry.assignments})
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        direct = next((item for item in registry.assignments if item.underlying_symbol == symbol and item.assignment_mode == "DIRECT" and item.enabled), None)
        shadows = [item for item in registry.assignments if item.underlying_symbol == symbol and item.assignment_mode == "SHADOW" and item.enabled]
        shadow_rows: list[dict[str, Any]] = []
        for assignment in shadows:
            strategy = by_id[assignment.strategy_id]
            ev = evidence.get((symbol, assignment.strategy_id), {})
            shadow_rows.append(
                {
                    "strategy_id": strategy.strategy_id,
                    "strategy_name": strategy.name,
                    "timeframe": strategy.timeframe,
                    "number_of_entries": strategy.number_of_entries,
                    "simulated_allocation": allocations.get(symbol),
                    "allocation_model": "SAME_PRIMARY_SHARE_QUANTITY_SIMULATED_ONLY",
                    "normalization_basis": "CURRENT_SWING_ALLOCATION",
                    "primary_reference_quantity": ev.get("primary_reference_quantity"),
                    "shadow_test_quantity": ev.get("shadow_test_quantity"),
                    "sizing_basis": ev.get("sizing_basis"),
                    "trade_count": ev.get("trade_count"),
                    "wins": ev.get("wins"),
                    "losses": ev.get("losses"),
                    "win_rate": ev.get("win_rate"),
                    "gross_profit": ev.get("gross_profit"),
                    "gross_loss": ev.get("gross_loss"),
                    "net_pl": ev.get("net_pl"),
                    "max_drawdown": ev.get("max_drawdown"),
                    "profit_factor": ev.get("profit_factor"),
                    "open_pl": ev.get("open_pl"),
                    "evidence_status": ev.get("evidence_status", "AWAITING_SHADOW_LEDGER"),
                    "promotion_recommended": bool(ev.get("promotion_recommended", False)),
                    "promotion_requires_affirmative_approval": False,
                    "user_veto_allowed": True,
                }
            )
        rows.append(
            {
                "underlying_symbol": symbol,
                "direct_strategy_id": None if direct is None else direct.strategy_id,
                "direct_strategy_name": None if direct is None else by_id[direct.strategy_id].name,
                "current_swing_allocation": allocations.get(symbol),
                "shadow_strategies": shadow_rows,
            }
        )

    return {
        "schema_version": "1.2",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "auto_promotion_enabled": True,
        "promotion_authority": "AUTOMATIC_AFTER_QUALIFICATION_AND_VETO_WINDOW",
        "affirmative_approval_required": False,
        "user_veto_allowed": True,
        "shadow_allocation_model": "SAME_PRIMARY_SHARE_QUANTITY_SIMULATED_ONLY",
        "shadow_sizing_basis": "PRIMARY_SHARE_QUANTITY",
        "normalization_basis": "CURRENT_SWING_ALLOCATION",
        "shadow_capital_reserved": False,
        "shadow_capital_movement_enabled": False,
        "rows": rows,
    }


def write_strategy_assignment_shadow_report(payload: Mapping[str, Any], *, output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return output_path


def build_and_write_strategy_assignment_shadow_report(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    allocation_path: Path = DEFAULT_ALLOCATION_PATH,
    shadow_performance_path: Path = DEFAULT_SHADOW_PERFORMANCE_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    payload = build_strategy_assignment_shadow_report(
        registry_path=registry_path,
        allocation_path=allocation_path,
        shadow_performance_path=shadow_performance_path,
    )
    write_strategy_assignment_shadow_report(payload, output_path=output_path)
    return payload


if __name__ == "__main__":
    result = build_and_write_strategy_assignment_shadow_report()
    print(f"Strategy assignment shadow report: {len(result['rows'])} symbols")

"""Synchronize governed paper allocation authority into existing Primary state.

This bridge never invents dollars. It only fills a missing/zero
``allocation_notional`` for an already-baselined frozen DIRECT Primary from the
combined AI CIO strategy-capital and Swing security-allocation authority.

Existing positive allocation_notional is preserved so a flat Primary can retain
its previously-authorized re-entry budget. Missing security allocation leaves the
state unchanged and therefore fail-closed at the execution boundary.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .frozen_primary_allocation_authority import (
    DEFAULT_PORTFOLIO_ALLOCATION_PATH,
    resolve_frozen_primary_allocation_authority,
)
from .frozen_primary_signal_execution_workflow import DEFAULT_STATE_PATH
from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, load_frozen_symbol_stacks

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


def synchronize_frozen_primary_allocation_state(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    state_path: Path = DEFAULT_STATE_PATH,
    portfolio_allocation_path: Path = DEFAULT_PORTFOLIO_ALLOCATION_PATH,
) -> dict[str, Any]:
    """Fill missing Primary allocation notionals from authoritative evidence.

    The signal-execution workflow deliberately establishes a non-retroactive
    baseline on first sight of a strategy. This sync therefore updates only
    strategy state that already exists; a brand-new strategy remains baseline-only
    on its first cycle and becomes allocation-eligible on a later cycle.
    """
    state_file = Path(state_path)
    if not state_file.is_file():
        return _report([], state_path=state_file, status="NO_EXECUTION_STATE")

    payload = _load_json_object(state_file)
    symbols = payload.get("symbols")
    if not isinstance(symbols, dict):
        raise ValueError("frozen Primary execution state must contain a symbols object")

    rows: list[dict[str, Any]] = []
    changed = False
    for stack in load_frozen_symbol_stacks(config_path):
        primary = stack.primary
        symbol = stack.symbol
        if not primary.enabled:
            rows.append(_row(symbol, primary.strategy_id, "PRIMARY_DISABLED"))
            continue

        current = symbols.get(symbol)
        if not isinstance(current, dict):
            rows.append(_row(symbol, primary.strategy_id, "NO_BASELINE_STATE"))
            continue
        if str(current.get("strategy_id", "")).strip() != primary.strategy_id:
            rows.append(_row(symbol, primary.strategy_id, "STATE_STRATEGY_MISMATCH"))
            continue

        existing = current.get("allocation_notional")
        if existing not in (None, "", 0, 0.0):
            rows.append({
                **_row(symbol, primary.strategy_id, "PRESERVED_EXISTING_AUTHORITY"),
                "allocation_notional": float(existing),
            })
            continue

        authority = resolve_frozen_primary_allocation_authority(
            signal_symbol=primary.signal_symbol,
            vehicle_symbol=primary.vehicle_symbol,
            portfolio_allocation_path=portfolio_allocation_path,
        )
        if authority is None:
            rows.append({
                **_row(symbol, primary.strategy_id, "NO_SECURITY_ALLOCATION_AUTHORITY"),
                "signal_symbol": primary.signal_symbol,
                "vehicle_symbol": primary.vehicle_symbol,
                "allocation_notional": None,
            })
            continue

        updated = dict(current)
        updated["allocation_notional"] = authority.authorized_notional
        updated["allocation_authority"] = authority.row()
        symbols[symbol] = updated
        changed = True
        rows.append({
            **_row(symbol, primary.strategy_id, "AUTHORIZED_FROM_PORTFOLIO_ALLOCATION"),
            "signal_symbol": primary.signal_symbol,
            "vehicle_symbol": primary.vehicle_symbol,
            "allocation_symbol": authority.allocation_symbol,
            "allocation_percent": authority.allocation_percent,
            "strategy_allocated_capital": authority.strategy_allocated_capital,
            "allocation_notional": authority.authorized_notional,
        })

    if changed:
        payload["symbols"] = symbols
        _atomic_json(state_file, payload)
    return _report(rows, state_path=state_file, status="UPDATED" if changed else "NO_CHANGE")


def _report(rows: list[dict[str, Any]], *, state_path: Path, status: str) -> dict[str, Any]:
    return {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "status": status,
        "state_path": str(state_path),
        "rows": rows,
    }


def _row(symbol: str, strategy_id: str, status: str) -> dict[str, Any]:
    return {"symbol": symbol, "strategy_id": strategy_id, "status": status}


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise

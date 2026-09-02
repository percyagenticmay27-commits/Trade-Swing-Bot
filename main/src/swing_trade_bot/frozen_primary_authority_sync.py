"""Synchronize frozen DIRECT strategy authority onto existing paper positions.

This bridge performs authority adoption only. It never creates or closes a paper
position, changes share quantity or cost basis, places an order, connects to a
broker, or moves capital. Signal-driven paper entry/exit remains a separate
milestone because the current ledger must first reconcile realized P/L on SELLs.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, load_frozen_symbol_stacks

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
PAPER_POSITION_CREATION_ENABLED = False
PAPER_POSITION_CLOSURE_ENABLED = False
SCHEMA_VERSION = "1.0"
DEFAULT_LEDGER_PATH = Path("results/paper_ledger/open_positions.json")
DEFAULT_REPORT_PATH = Path("results/frozen_primary_authority_sync.json")


def synchronize_frozen_primary_authority(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> dict[str, Any]:
    """Adopt each frozen DIRECT strategy onto an existing paper holding.

    Only ``active_strategy`` may change. Every economic field of the position is
    preserved byte-for-value from the input object. A symbol without an existing
    paper position is reported but no position is fabricated.
    """
    stacks = load_frozen_symbol_stacks(config_path)
    payload = _load_object(ledger_path)
    if payload.get("paper_trade_mode", True) is not True:
        raise ValueError("open_positions ledger must be paper_trade_mode=true")
    rows = payload.get("positions")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("open_positions ledger must contain a positions list of objects")

    positions = [dict(row) for row in rows]
    by_symbol: dict[str, int] = {}
    for index, row in enumerate(positions):
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("paper position symbol is required")
        if symbol in by_symbol:
            raise ValueError(f"duplicate open paper position for {symbol}")
        by_symbol[symbol] = index

    results: list[dict[str, Any]] = []
    changed = False
    for stack in stacks:
        primary = stack.primary
        if not primary.enabled:
            results.append({
                "symbol": stack.symbol,
                "strategy_id": primary.strategy_id,
                "status": "PRIMARY_DISABLED",
                "position_changed": False,
            })
            continue
        index = by_symbol.get(stack.symbol)
        if index is None:
            results.append({
                "symbol": stack.symbol,
                "strategy_id": primary.strategy_id,
                "status": "NO_OPEN_POSITION",
                "position_changed": False,
            })
            continue
        before = dict(positions[index])
        prior_strategy = str(before.get("active_strategy", ""))
        after = dict(before)
        after["active_strategy"] = primary.strategy_id
        positions[index] = after
        adopted = prior_strategy != primary.strategy_id
        changed = changed or adopted
        _assert_only_strategy_changed(before, after)
        results.append({
            "symbol": stack.symbol,
            "strategy_id": primary.strategy_id,
            "prior_active_strategy": prior_strategy,
            "status": "ADOPTED" if adopted else "ALREADY_ACTIVE",
            "position_changed": adopted,
            "shares": after.get("shares"),
            "cost_basis": after.get("cost_basis"),
        })

    if changed:
        updated = dict(payload)
        updated["positions"] = positions
        _atomic_json(ledger_path, updated)

    report = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": "SWING-001",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "paper_position_creation_enabled": False,
        "paper_position_closure_enabled": False,
        "authority_scope": "ACTIVE_STRATEGY_FIELD_ONLY",
        "position_count_changed": 0,
        "share_quantity_changed": False,
        "cost_basis_changed": False,
        "rows": results,
    }
    _atomic_json(report_path, report)
    return report


def _assert_only_strategy_changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    before_without = {key: value for key, value in before.items() if key != "active_strategy"}
    after_without = {key: value for key, value in after.items() if key != "active_strategy"}
    if before_without != after_without:
        raise ValueError("frozen Primary authority sync may change only active_strategy")


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

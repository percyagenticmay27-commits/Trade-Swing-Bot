"""One-time migration for pre-v1.1 frozen Primary raw-stop cursors.

Older frozen Primary execution state contains the original activation timestamp
but no raw intraday catastrophic-stop cursor.  This migration preserves the
non-retroactive deployment boundary by seeding the missing raw-stop cursor from
that original activation timestamp, not from the latest market-data row.

It mutates execution state only.  It never creates/closes paper positions,
executes strategy events, places orders, or moves capital.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
PAPER_POSITION_CREATION_ENABLED = False
PAPER_POSITION_CLOSURE_ENABLED = False
DEFAULT_STATE_PATH = Path("results/frozen_primary_signal_execution_state.json")


def migrate_missing_stop_cursors(*, state_path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    """Seed missing stop cursors from each symbol's original activation time."""
    path = Path(state_path)
    payload = _load_object(path)
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("frozen Primary execution state must be paper_trade_mode=true")
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, Mapping):
        raise ValueError("frozen Primary execution state must contain symbols object")

    symbols: dict[str, Any] = dict(raw_symbols)
    rows: list[dict[str, Any]] = []
    changed = False

    for symbol, raw_state in raw_symbols.items():
        if not isinstance(raw_state, Mapping):
            raise ValueError(f"symbol state must be an object: {symbol}")
        state = dict(raw_state)
        existing = str(state.get("last_processed_stop_raw_bar", "")).strip()
        if existing:
            _parse_aware(existing, "last_processed_stop_raw_bar")
            rows.append({
                "symbol": str(symbol).upper(),
                "status": "ALREADY_MIGRATED",
                "last_processed_stop_raw_bar": existing,
            })
            continue

        initialized = str(state.get("initialized_at_utc", "")).strip()
        if not initialized:
            raise ValueError(
                f"cannot safely migrate {symbol}: initialized_at_utc is missing"
            )
        activation = _parse_aware(initialized, "initialized_at_utc")
        activation_utc = activation.astimezone(timezone.utc).replace(microsecond=0)
        cursor = activation_utc.isoformat().replace("+00:00", "Z")

        state["last_processed_stop_raw_bar"] = cursor
        state["stop_cursor_migration_source"] = "ORIGINAL_PRIMARY_ACTIVATION_TIMESTAMP"
        state["stop_cursor_migrated_at_utc"] = _utc_now()
        symbols[str(symbol)] = state
        changed = True
        rows.append({
            "symbol": str(symbol).upper(),
            "status": "MIGRATED_FROM_ACTIVATION_TIMESTAMP",
            "initialized_at_utc": initialized,
            "last_processed_stop_raw_bar": cursor,
        })

    if changed:
        updated = dict(payload)
        updated["symbols"] = symbols
        _atomic_json(path, updated)

    return {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "paper_position_creation_enabled": False,
        "paper_position_closure_enabled": False,
        "state_path": str(path),
        "state_changed": changed,
        "rows": rows,
    }


def _parse_aware(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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

"""Authoritative Phase 2.1 paper-ledger foundation for SWING-001.

Creates and validates the canonical paper-only ledger artifacts without
inventing positions or changing strategy calculations. Existing execution
outputs are normalized into stable JSON/CSV projections for downstream use.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
STRATEGY_ID = "SWING-001"
SWING_ALLOCATION = 4500.0
PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


def initialize_paper_ledger(ledger_dir: Path) -> dict[str, Any]:
    """Create missing canonical ledger files atomically, preserving all evidence."""
    ledger_dir = Path(ledger_dir)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    open_path = ledger_dir / "open_positions.json"
    trade_path = ledger_dir / "trade_history.json"
    managed_path = ledger_dir / "managed_trade_history.json"

    if not open_path.exists():
        _atomic_json(open_path, _base_payload(generated_at, positions=[]))
    if not trade_path.exists():
        _atomic_json(trade_path, _base_payload(generated_at, trades=[]))

    open_payload = _load_object(open_path)
    trade_payload = _load_object(trade_path)
    positions = _list_field(open_payload, "positions", open_path)
    trades = _list_field(trade_payload, "trades", trade_path)

    managed_payload = {
        **_safety(generated_at),
        "trade_count": len(trades),
        "trades": trades,
    }
    _atomic_json(managed_path, managed_payload)
    _write_positions_csv(ledger_dir / "paper_portfolio_positions.csv", positions)
    _write_performance_csv(ledger_dir / "paper_performance.csv", positions)

    status = {
        **_safety(generated_at),
        "status": "READY",
        "position_count": len(positions),
        "trade_count": len(trades),
        "artifacts": {
            "open_positions": str(open_path),
            "trade_history": str(trade_path),
            "managed_trade_history": str(managed_path),
            "paper_portfolio_positions": str(ledger_dir / "paper_portfolio_positions.csv"),
            "paper_performance": str(ledger_dir / "paper_performance.csv"),
        },
        "warnings": [] if positions else ["No open paper positions exist yet."],
    }
    _atomic_json(ledger_dir / "paper_ledger_status.json", status)
    return status


def _base_payload(generated_at: str, **values: Any) -> dict[str, Any]:
    return {**_safety(generated_at), **values}


def _safety(generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "allocated_capital": SWING_ALLOCATION,
        "generated_at": generated_at,
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
    }


def _write_positions_csv(path: Path, positions: list[dict[str, Any]]) -> None:
    fields = ["symbol", "status", "entry_date", "entry_price", "shares", "cost_basis", "current_price", "market_value", "unrealized_pnl", "unrealized_pnl_percent", "allocation_percent", "active_strategy"]
    _atomic_csv(path, fields, [{field: row.get(field, "") for field in fields} for row in positions])


def _write_performance_csv(path: Path, positions: list[dict[str, Any]]) -> None:
    fields = ["symbol", "cost_basis", "market_value", "unrealized_pnl", "unrealized_pnl_percent", "status"]
    _atomic_csv(path, fields, [{field: row.get(field, "") for field in fields} for row in positions])


def _atomic_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try: os.unlink(temp_name)
        except FileNotFoundError: pass
        raise


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, sort_keys=True)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try: os.unlink(temp_name)
        except FileNotFoundError: pass
        raise


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _list_field(payload: Mapping[str, Any], field: str, path: Path) -> list[dict[str, Any]]:
    rows = payload.get(field)
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError(f"{path} must contain a {field} list of objects")
    return [dict(row) for row in rows]

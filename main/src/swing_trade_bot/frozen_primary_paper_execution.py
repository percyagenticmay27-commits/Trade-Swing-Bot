"""Paper-only execution boundary for frozen DIRECT Primary strategies.

This module is the only frozen-strategy component allowed to mutate the Swing
paper ledger. It never connects to a broker, never places a real order, and never
moves real capital. SHADOW strategies are rejected explicitly.

Signal generation/timing is intentionally separate: callers must provide a
fully-resolved paper execution event (ENTRY or EXIT) with its authoritative
paper fill timestamp and price. This keeps strategy-signal semantics separate
from the persistent ledger mutation boundary and makes the boundary testable.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, resolve_frozen_stack

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
SHADOW_EXECUTION_ENABLED = False
SCHEMA_VERSION = "1.0"
DEFAULT_LEDGER_DIR = Path("results/paper_ledger")


@dataclass(frozen=True, slots=True)
class FrozenPrimaryExecutionEvent:
    symbol: str
    strategy_id: str
    side: str
    execution_timestamp: str
    price: float
    reason: str
    target_notional: float | None = None
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        strategy_id = self.strategy_id.strip().upper()
        side = self.side.strip().upper()
        if not symbol or self.symbol != symbol:
            raise ValueError("symbol must be uppercase and trimmed")
        if not strategy_id or self.strategy_id != strategy_id:
            raise ValueError("strategy_id must be uppercase and trimmed")
        if side not in {"BUY", "SELL"} or self.side != side:
            raise ValueError("side must be BUY or SELL")
        if not math.isfinite(self.price) or self.price <= 0:
            raise ValueError("price must be positive and finite")
        if not self.reason.strip():
            raise ValueError("reason is required")
        if self.target_notional is not None and (
            not math.isfinite(self.target_notional) or self.target_notional <= 0
        ):
            raise ValueError("target_notional must be positive and finite")
        try:
            parsed = datetime.fromisoformat(self.execution_timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("execution_timestamp must be ISO-8601") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("execution_timestamp must be timezone-aware")
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")


def execute_frozen_primary_event(
    event: FrozenPrimaryExecutionEvent,
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    ledger_dir: Path = DEFAULT_LEDGER_DIR,
) -> dict[str, Any]:
    """Apply one resolved frozen DIRECT event to the paper ledger.

    BUY creates one paper position using ``target_notional``. SELL closes the
    entire current paper position for the symbol. The function is idempotent by
    deterministic trade_id and fails closed on inconsistent ledger state.
    """
    stack = resolve_frozen_stack(event.symbol, config_path)
    if stack is None:
        raise ValueError(f"no frozen stack for {event.symbol}")
    primary = stack.primary
    if primary.strategy_id != event.strategy_id or primary.assignment_mode != "DIRECT":
        raise ValueError("only the current frozen DIRECT Primary may execute")
    if not primary.enabled:
        raise ValueError("frozen DIRECT Primary is disabled")

    ledger_dir = Path(ledger_dir)
    open_path = ledger_dir / "open_positions.json"
    history_path = ledger_dir / "trade_history.json"
    open_payload = _load_object(open_path)
    history_payload = _load_object(history_path)
    if open_payload.get("paper_trade_mode", True) is not True:
        raise ValueError("open_positions ledger must be paper_trade_mode=true")
    if history_payload.get("paper_trade_mode", True) is not True:
        raise ValueError("trade_history ledger must be paper_trade_mode=true")

    raw_positions = open_payload.get("positions")
    raw_trades = history_payload.get("trades")
    if not isinstance(raw_positions, list) or any(not isinstance(row, Mapping) for row in raw_positions):
        raise ValueError("open_positions ledger must contain a positions list of objects")
    if not isinstance(raw_trades, list) or any(not isinstance(row, Mapping) for row in raw_trades):
        raise ValueError("trade_history ledger must contain a trades list of objects")

    positions = [dict(row) for row in raw_positions]
    trades = [dict(row) for row in raw_trades]
    matching = [row for row in positions if str(row.get("symbol", "")).strip().upper() == event.symbol]
    if len(matching) > 1:
        raise ValueError(f"duplicate open paper position for {event.symbol}")
    current = matching[0] if matching else None

    trade_id = _trade_id(event)
    existing_trade = next((row for row in trades if str(row.get("trade_id", "")) == trade_id), None)
    if existing_trade is not None:
        return {
            **_safety(),
            "status": "ALREADY_APPLIED",
            "symbol": event.symbol,
            "strategy_id": event.strategy_id,
            "trade_id": trade_id,
            "position_changed": False,
        }

    if event.side == "SELL":
        if current is None:
            raise ValueError(f"cannot SELL {event.symbol}: no open paper position")
        if str(current.get("active_strategy", "")).strip().upper() != event.strategy_id:
            raise ValueError("open paper position is not controlled by the current frozen DIRECT Primary")
        shares = _positive(current.get("shares"), "position.shares")
        notional = round(shares * event.price, 2)
        positions = [row for row in positions if row is not current]
        trade = _trade_row(event, trade_id=trade_id, shares=shares, notional=notional)
        status = "PAPER_POSITION_CLOSED"
    else:
        if current is not None:
            raise ValueError(f"cannot BUY {event.symbol}: paper position already open")
        if event.target_notional is None:
            raise ValueError("BUY requires target_notional")
        shares = round(event.target_notional / event.price, 8)
        if shares <= 0:
            raise ValueError("BUY target_notional produces zero shares")
        cost_basis = round(shares * event.price, 2)
        allocation_percent = 0.0
        position = {
            "symbol": event.symbol,
            "opened_at": event.execution_timestamp,
            "entry_date": event.execution_timestamp[:10],
            "entry_price": event.price,
            "shares": shares,
            "cost_basis": cost_basis,
            "current_price": event.price,
            "market_value": cost_basis,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_percent": 0.0,
            "allocation_percent": allocation_percent,
            "active_strategy": event.strategy_id,
            "status": "OPEN",
        }
        positions.append(position)
        trade = _trade_row(event, trade_id=trade_id, shares=shares, notional=cost_basis)
        status = "PAPER_POSITION_OPENED"

    trades.append(trade)
    updated_open = dict(open_payload)
    updated_open["positions"] = positions
    updated_history = dict(history_payload)
    updated_history["trades"] = trades

    # Each artifact is atomically replaced. The deterministic trade ID makes a
    # retry safe if a process interruption occurs after one replacement.
    _atomic_json(open_path, updated_open)
    _atomic_json(history_path, updated_history)

    return {
        **_safety(),
        "status": status,
        "symbol": event.symbol,
        "strategy_id": event.strategy_id,
        "trade_id": trade_id,
        "side": event.side,
        "price": event.price,
        "shares": shares,
        "notional": trade["notional"],
        "position_changed": True,
    }


def _trade_id(event: FrozenPrimaryExecutionEvent) -> str:
    stamp = event.execution_timestamp.replace(":", "").replace("-", "").replace("+", "_")
    return f"FROZEN-{event.symbol}-{event.strategy_id}-{stamp}-{event.side}"


def _trade_row(
    event: FrozenPrimaryExecutionEvent,
    *,
    trade_id: str,
    shares: float,
    notional: float,
) -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "symbol": event.symbol,
        "side": event.side,
        "trade_date": event.execution_timestamp[:10],
        "price": event.price,
        "shares": round(shares, 8),
        "notional": round(notional, 2),
        "active_strategy": event.strategy_id,
        "reason": event.reason,
        "paper_trade_mode": True,
        "execution_timestamp": event.execution_timestamp,
        "execution_authority": "FROZEN_DIRECT_PRIMARY",
    }


def _positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be positive and finite")
    return number


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


def _safety() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": "SWING-001",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "shadow_execution_enabled": False,
    }

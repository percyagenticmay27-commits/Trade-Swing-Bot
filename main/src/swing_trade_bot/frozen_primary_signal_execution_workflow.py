"""Paper-only signal-to-execution workflow for frozen DIRECT Primary strategies.

This workflow bridges the frozen signal engine to the governed paper-ledger
execution boundary.  It processes only the current DIRECT Primary for each
frozen symbol stack.  SHADOW strategies remain research-only.

The first run establishes a non-retroactive cursor at the latest available chart
bar and adopts no historical signal.  Later runs process only chart bars newer
than that cursor.  Confirmed strategy signals execute at the next chart-bar open,
matching the frozen research contract.  A pending signal is persisted when its
next chart bar is not available yet.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .frozen_ai_signal_engines import evaluate_frozen_signal
from .frozen_primary_paper_execution import (
    FrozenPrimaryExecutionEvent,
    execute_frozen_primary_event,
)
from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, load_frozen_symbol_stacks
from .intraday_chart_bars import build_chart_bars, load_intraday_csv, regular_session_rows

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
SHADOW_EXECUTION_ENABLED = False
SCHEMA_VERSION = "1.0"
DEFAULT_INTRADAY_DIR = Path("data/intraday")
DEFAULT_LEDGER_DIR = Path("results/paper_ledger")
DEFAULT_STATE_PATH = Path("results/frozen_primary_signal_execution_state.json")
DEFAULT_REPORT_PATH = Path("results/frozen_primary_signal_execution_report.json")


def run_frozen_primary_signal_execution(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    intraday_dir: Path = DEFAULT_INTRADAY_DIR,
    ledger_dir: Path = DEFAULT_LEDGER_DIR,
    state_path: Path = DEFAULT_STATE_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    source_timezone: str = "America/New_York",
) -> dict[str, Any]:
    """Process new frozen DIRECT Primary chart bars into paper-only events."""
    stacks = load_frozen_symbol_stacks(config_path)
    state = _load_state(state_path)
    symbols_state = dict(state.get("symbols", {}))
    rows: list[dict[str, Any]] = []

    for stack in stacks:
        primary = stack.primary
        symbol = stack.symbol
        if not primary.enabled:
            rows.append(_row(symbol, primary.strategy_id, "PRIMARY_DISABLED"))
            continue

        market_path = Path(intraday_dir) / f"{symbol}.csv"
        if not market_path.is_file():
            rows.append(_row(symbol, primary.strategy_id, "MISSING_INTRADAY_MARKET_DATA"))
            continue

        try:
            raw_rows = load_intraday_csv(market_path, source_timezone=source_timezone)
            session_rows = regular_session_rows(raw_rows)
            chart_bars = build_chart_bars(session_rows, primary.timeframe)  # type: ignore[arg-type]
        except (OSError, ValueError, TypeError) as exc:
            rows.append(_row(symbol, primary.strategy_id, "MARKET_DATA_ERROR", error=f"{type(exc).__name__}: {exc}"))
            continue
        if not chart_bars:
            rows.append(_row(symbol, primary.strategy_id, "NO_CHART_BARS"))
            continue

        symbol_state = dict(symbols_state.get(symbol, {}))
        latest_timestamp = chart_bars[-1].timestamp.isoformat()
        if not symbol_state:
            budget = _current_position_cost_basis(Path(ledger_dir), symbol)
            symbols_state[symbol] = {
                "strategy_id": primary.strategy_id,
                "last_processed_chart_bar": latest_timestamp,
                "pending_signal": None,
                "allocation_notional": budget,
                "initialized_at_utc": _utc_now(),
            }
            rows.append({
                **_row(symbol, primary.strategy_id, "BASELINE_INITIALIZED"),
                "last_processed_chart_bar": latest_timestamp,
                "allocation_notional": budget,
                "executed_events": [],
            })
            continue

        # Promotion changes DIRECT authority without retroactively replaying the new
        # strategy over old bars.  Re-baseline that symbol from the current bar.
        if str(symbol_state.get("strategy_id", "")) != primary.strategy_id:
            symbol_state["strategy_id"] = primary.strategy_id
            symbol_state["last_processed_chart_bar"] = latest_timestamp
            symbol_state["pending_signal"] = None
            if symbol_state.get("allocation_notional") in (None, 0, 0.0):
                symbol_state["allocation_notional"] = _current_position_cost_basis(Path(ledger_dir), symbol)
            symbols_state[symbol] = symbol_state
            rows.append({
                **_row(symbol, primary.strategy_id, "PRIMARY_CHANGE_REBASELINED"),
                "last_processed_chart_bar": latest_timestamp,
                "executed_events": [],
            })
            continue

        try:
            result = _process_symbol(
                symbol=symbol,
                primary=primary,
                chart_bars=chart_bars,
                ledger_dir=Path(ledger_dir),
                config_path=Path(config_path),
                symbol_state=symbol_state,
            )
        except (OSError, ValueError, TypeError) as exc:
            rows.append(_row(symbol, primary.strategy_id, "EXECUTION_ERROR", error=f"{type(exc).__name__}: {exc}"))
            continue
        symbols_state[symbol] = result.pop("state")
        rows.append(result)

    updated_state = {
        **_safety(),
        "symbols": symbols_state,
    }
    _atomic_json(state_path, updated_state)
    report = {
        **_safety(),
        "execution_scope": "FROZEN_DIRECT_PRIMARY_ONLY",
        "shadow_execution_enabled": False,
        "rows": rows,
    }
    _atomic_json(report_path, report)
    return report


def _process_symbol(*, symbol, primary, chart_bars, ledger_dir: Path, config_path: Path, symbol_state: dict[str, Any]) -> dict[str, Any]:
    last_processed = str(symbol_state.get("last_processed_chart_bar", ""))
    if not last_processed:
        raise ValueError("last_processed_chart_bar is required after initialization")
    timestamps = [bar.timestamp.isoformat() for bar in chart_bars]
    index_by_timestamp = {value: index for index, value in enumerate(timestamps)}
    if last_processed not in index_by_timestamp:
        raise ValueError("saved chart-bar cursor is no longer present in intraday archive")

    pending = symbol_state.get("pending_signal")
    executed: list[dict[str, Any]] = []
    start_index = index_by_timestamp[last_processed] + 1

    # A signal confirmed on the prior run executes at the next chart-bar open.
    if isinstance(pending, Mapping) and start_index < len(chart_bars):
        fill_bar = chart_bars[start_index]
        event = _event_from_pending(
            symbol=symbol,
            strategy_id=primary.strategy_id,
            pending=pending,
            fill_timestamp=fill_bar.timestamp.isoformat(),
            fill_price=fill_bar.open,
            target_notional=_allocation_notional(symbol_state),
        )
        applied = execute_frozen_primary_event(event, config_path=config_path, ledger_dir=ledger_dir)
        executed.append(applied)
        pending = None

    for index in range(start_index, len(chart_bars)):
        bar = chart_bars[index]
        decision = evaluate_frozen_signal(primary.engine_id, primary.parameters, chart_bars[: index + 1])
        position_open = _has_open_position(ledger_dir, symbol)
        desired_side = None
        reason = None
        if position_open and decision.exit_signal:
            desired_side = "SELL"
            reason = "FROZEN_DIRECT_PRIMARY_CONFIRMED_TECHNICAL_EXIT"
        elif not position_open and decision.entry_signal:
            desired_side = "BUY"
            reason = "FROZEN_DIRECT_PRIMARY_CONFIRMED_ENTRY"

        if desired_side is not None:
            if index + 1 < len(chart_bars):
                fill_bar = chart_bars[index + 1]
                event = FrozenPrimaryExecutionEvent(
                    symbol=symbol,
                    strategy_id=primary.strategy_id,
                    side=desired_side,
                    execution_timestamp=fill_bar.timestamp.isoformat(),
                    price=fill_bar.open,
                    reason=reason,
                    target_notional=_allocation_notional(symbol_state) if desired_side == "BUY" else None,
                )
                applied = execute_frozen_primary_event(event, config_path=config_path, ledger_dir=ledger_dir)
                executed.append(applied)
                # Do not independently evaluate the fill bar for another signal;
                # it is the execution bar for the just-confirmed event.
                symbol_state["last_processed_chart_bar"] = fill_bar.timestamp.isoformat()
                pending = None
                continue
            pending = {
                "side": desired_side,
                "signal_chart_bar": bar.timestamp.isoformat(),
                "reason": reason,
            }

        symbol_state["last_processed_chart_bar"] = bar.timestamp.isoformat()

    symbol_state["pending_signal"] = pending
    return {
        **_row(symbol, primary.strategy_id, "PROCESSED"),
        "last_processed_chart_bar": symbol_state["last_processed_chart_bar"],
        "pending_signal": pending,
        "executed_events": executed,
        "state": symbol_state,
    }


def _event_from_pending(*, symbol: str, strategy_id: str, pending: Mapping[str, Any], fill_timestamp: str, fill_price: float, target_notional: float | None) -> FrozenPrimaryExecutionEvent:
    side = str(pending.get("side", "")).upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("pending signal side must be BUY or SELL")
    return FrozenPrimaryExecutionEvent(
        symbol=symbol,
        strategy_id=strategy_id,
        side=side,
        execution_timestamp=fill_timestamp,
        price=fill_price,
        reason=str(pending.get("reason", "FROZEN_DIRECT_PRIMARY_PENDING_SIGNAL")),
        target_notional=target_notional if side == "BUY" else None,
    )


def _allocation_notional(symbol_state: Mapping[str, Any]) -> float:
    value = symbol_state.get("allocation_notional")
    if value is None:
        raise ValueError("frozen Primary reentry requires preserved allocation_notional")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("allocation_notional must be positive and finite")
    return number


def _current_position_cost_basis(ledger_dir: Path, symbol: str) -> float | None:
    payload = _load_object(ledger_dir / "open_positions.json")
    rows = payload.get("positions")
    if not isinstance(rows, list):
        raise ValueError("open_positions ledger must contain a positions list")
    matches = [row for row in rows if isinstance(row, Mapping) and str(row.get("symbol", "")).strip().upper() == symbol]
    if len(matches) > 1:
        raise ValueError(f"duplicate open paper position for {symbol}")
    if not matches:
        return None
    value = float(matches[0].get("cost_basis"))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("open position cost_basis must be positive and finite")
    return value


def _has_open_position(ledger_dir: Path, symbol: str) -> bool:
    payload = _load_object(ledger_dir / "open_positions.json")
    rows = payload.get("positions")
    if not isinstance(rows, list):
        raise ValueError("open_positions ledger must contain a positions list")
    matches = [row for row in rows if isinstance(row, Mapping) and str(row.get("symbol", "")).strip().upper() == symbol]
    if len(matches) > 1:
        raise ValueError(f"duplicate open paper position for {symbol}")
    return bool(matches)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {**_safety(), "symbols": {}}
    payload = _load_object(path)
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("frozen Primary signal execution state must be paper_trade_mode=true")
    if not isinstance(payload.get("symbols"), Mapping):
        raise ValueError("frozen Primary signal execution state must contain symbols object")
    return payload


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _row(symbol: str, strategy_id: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"symbol": symbol, "strategy_id": strategy_id, "status": status, **extra}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safety() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": "SWING-001",
        "generated_at_utc": _utc_now(),
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "shadow_execution_enabled": False,
    }


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

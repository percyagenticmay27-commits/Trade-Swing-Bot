"""Paper-only signal-to-execution workflow for frozen DIRECT Primary strategies.

This workflow bridges the frozen signal engine to the governed paper-ledger
execution boundary. It processes only the current DIRECT Primary for each
frozen symbol stack. SHADOW strategies remain research-only.

Signal bars come from each strategy's ``signal_symbol`` while paper fills and
catastrophic-stop evidence come from its ``vehicle_symbol``. This preserves the
same-symbol SOXL path and also supports explicit underlying-signal / leveraged-
vehicle mappings such as QQQ -> TQQQ without treating QQQ prices as TQQQ fills.

The first run establishes non-retroactive chart and raw-stop cursors. Later runs
process only chart bars and raw NY-RTH rows newer than those cursors. Confirmed
strategy signals execute at the next chart-bar open using the vehicle's open. A
configured catastrophic stop is monitored against raw intraday vehicle rows
while the DIRECT Primary position is open and exits at the vehicle stop price.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .frozen_ai_signal_engines import evaluate_frozen_signal
from .frozen_primary_paper_execution import (
    FrozenPrimaryExecutionEvent,
    execute_frozen_primary_event,
)
from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, load_frozen_symbol_stacks
from .intraday_chart_bars import IntradayBar, build_chart_bars, load_intraday_csv, regular_session_rows

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
SHADOW_EXECUTION_ENABLED = False
SCHEMA_VERSION = "1.2"
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
    """Process new frozen DIRECT Primary signals and vehicle stop evidence."""
    stacks = load_frozen_symbol_stacks(config_path)
    state = _load_state(state_path)
    symbols_state = dict(state.get("symbols", {}))
    rows: list[dict[str, Any]] = []

    for stack in stacks:
        primary = stack.primary
        symbol = stack.symbol
        signal_symbol = primary.signal_symbol
        vehicle_symbol = primary.vehicle_symbol
        if vehicle_symbol != symbol:
            rows.append(_row(symbol, primary.strategy_id, "INVALID_VEHICLE_STACK_MAPPING"))
            continue
        if not primary.enabled:
            rows.append(_row(symbol, primary.strategy_id, "PRIMARY_DISABLED"))
            continue

        signal_path = Path(intraday_dir) / f"{signal_symbol}.csv"
        vehicle_path = Path(intraday_dir) / f"{vehicle_symbol}.csv"
        if not signal_path.is_file() or not vehicle_path.is_file():
            rows.append(_row(
                symbol,
                primary.strategy_id,
                "MISSING_INTRADAY_MARKET_DATA",
                signal_symbol=signal_symbol,
                vehicle_symbol=vehicle_symbol,
                signal_data_available=signal_path.is_file(),
                vehicle_data_available=vehicle_path.is_file(),
            ))
            continue

        try:
            signal_raw_rows = load_intraday_csv(signal_path, source_timezone=source_timezone)
            signal_session_rows = regular_session_rows(signal_raw_rows)
            signal_chart_bars = build_chart_bars(signal_session_rows, primary.timeframe)  # type: ignore[arg-type]
            completed_signal_bars = _completed_chart_bars(signal_chart_bars, signal_session_rows, primary.timeframe)

            if signal_path == vehicle_path:
                vehicle_session_rows = signal_session_rows
                vehicle_chart_bars = signal_chart_bars
            else:
                vehicle_raw_rows = load_intraday_csv(vehicle_path, source_timezone=source_timezone)
                vehicle_session_rows = regular_session_rows(vehicle_raw_rows)
                vehicle_chart_bars = build_chart_bars(vehicle_session_rows, primary.timeframe)  # type: ignore[arg-type]
        except (OSError, ValueError, TypeError) as exc:
            rows.append(_row(symbol, primary.strategy_id, "MARKET_DATA_ERROR", error=f"{type(exc).__name__}: {exc}"))
            continue
        if not signal_chart_bars or not vehicle_chart_bars:
            rows.append(_row(symbol, primary.strategy_id, "NO_CHART_BARS"))
            continue
        if not completed_signal_bars:
            rows.append(_row(symbol, primary.strategy_id, "NO_COMPLETED_CHART_BARS"))
            continue
        if not vehicle_session_rows:
            rows.append(_row(symbol, primary.strategy_id, "NO_VEHICLE_SESSION_ROWS"))
            continue

        symbol_state = dict(symbols_state.get(symbol, {}))
        latest_timestamp = completed_signal_bars[-1].timestamp.isoformat()
        latest_raw_timestamp = vehicle_session_rows[-1].timestamp.isoformat()
        if not symbol_state:
            budget = _current_position_cost_basis(Path(ledger_dir), vehicle_symbol)
            symbols_state[symbol] = {
                "strategy_id": primary.strategy_id,
                "signal_symbol": signal_symbol,
                "vehicle_symbol": vehicle_symbol,
                "last_processed_chart_bar": latest_timestamp,
                "last_processed_stop_raw_bar": latest_raw_timestamp,
                "pending_signal": None,
                "allocation_notional": budget,
                "initialized_at_utc": _utc_now(),
            }
            rows.append({
                **_row(symbol, primary.strategy_id, "BASELINE_INITIALIZED"),
                "signal_symbol": signal_symbol,
                "vehicle_symbol": vehicle_symbol,
                "last_processed_chart_bar": latest_timestamp,
                "last_processed_stop_raw_bar": latest_raw_timestamp,
                "allocation_notional": budget,
                "catastrophic_stop_percent": primary.catastrophic_stop_percent,
                "executed_events": [],
            })
            continue

        # Promotion changes DIRECT authority without retroactively replaying the new
        # strategy over old chart bars or raw stop history.
        if str(symbol_state.get("strategy_id", "")) != primary.strategy_id:
            symbol_state["strategy_id"] = primary.strategy_id
            symbol_state["signal_symbol"] = signal_symbol
            symbol_state["vehicle_symbol"] = vehicle_symbol
            symbol_state["last_processed_chart_bar"] = latest_timestamp
            symbol_state["last_processed_stop_raw_bar"] = latest_raw_timestamp
            symbol_state["pending_signal"] = None
            if symbol_state.get("allocation_notional") in (None, 0, 0.0):
                symbol_state["allocation_notional"] = _current_position_cost_basis(Path(ledger_dir), vehicle_symbol)
            symbols_state[symbol] = symbol_state
            rows.append({
                **_row(symbol, primary.strategy_id, "PRIMARY_CHANGE_REBASELINED"),
                "signal_symbol": signal_symbol,
                "vehicle_symbol": vehicle_symbol,
                "last_processed_chart_bar": latest_timestamp,
                "last_processed_stop_raw_bar": latest_raw_timestamp,
                "catastrophic_stop_percent": primary.catastrophic_stop_percent,
                "executed_events": [],
            })
            continue

        saved_signal_symbol = str(symbol_state.get("signal_symbol", signal_symbol)).strip().upper()
        saved_vehicle_symbol = str(symbol_state.get("vehicle_symbol", vehicle_symbol)).strip().upper()
        if saved_signal_symbol != signal_symbol or saved_vehicle_symbol != vehicle_symbol:
            raise ValueError("frozen Primary signal/vehicle mapping changed without a new strategy_id")
        symbol_state["signal_symbol"] = signal_symbol
        symbol_state["vehicle_symbol"] = vehicle_symbol

        # State written before schema 1.1 has no raw-stop cursor. Migrate it
        # non-retroactively at the latest available vehicle raw row rather than
        # replaying historical lows against an already-open paper position.
        if not str(symbol_state.get("last_processed_stop_raw_bar", "")):
            symbol_state["last_processed_stop_raw_bar"] = latest_raw_timestamp
            symbol_state["stop_cursor_migrated_at_utc"] = _utc_now()

        try:
            result = _process_symbol(
                symbol=symbol,
                primary=primary,
                signal_chart_bars=signal_chart_bars,
                completed_signal_bars=completed_signal_bars,
                vehicle_chart_bars=vehicle_chart_bars,
                vehicle_raw_rows=vehicle_session_rows,
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
        "signal_price_authority": "NY_RTH_INTRADAY_SIGNAL_SYMBOL",
        "paper_fill_price_authority": "NY_RTH_INTRADAY_VEHICLE_SYMBOL",
        "catastrophic_stop_authority": "RAW_NY_RTH_INTRADAY_VEHICLE_ROWS",
        "shadow_execution_enabled": False,
        "rows": rows,
    }
    _atomic_json(report_path, report)
    return report


def _completed_chart_bars(chart_bars, session_rows, timeframe: str):
    """Return only chart bars whose full frozen NY-RTH bucket has elapsed."""
    if not session_rows:
        return []
    latest_raw = session_rows[-1].timestamp
    completed = []
    for bar in chart_bars:
        local = bar.timestamp
        if timeframe == "1H":
            if local.hour == 15 and local.minute == 30:
                cutoff = local + timedelta(minutes=29)
            else:
                cutoff = local + timedelta(minutes=59)
        elif timeframe == "4H":
            cutoff = local + timedelta(minutes=239 if local.hour == 9 else 149)
        else:
            cutoff = local + timedelta(minutes=389)
        if latest_raw >= cutoff:
            completed.append(bar)
    return completed


def _process_symbol(
    *,
    symbol,
    primary,
    signal_chart_bars,
    completed_signal_bars,
    vehicle_chart_bars,
    vehicle_raw_rows: Sequence[IntradayBar],
    ledger_dir: Path,
    config_path: Path,
    symbol_state: dict[str, Any],
) -> dict[str, Any]:
    last_processed = str(symbol_state.get("last_processed_chart_bar", ""))
    if not last_processed:
        raise ValueError("last_processed_chart_bar is required after initialization")
    timestamps = [bar.timestamp.isoformat() for bar in signal_chart_bars]
    index_by_timestamp = {value: index for index, value in enumerate(timestamps)}
    if last_processed not in index_by_timestamp:
        raise ValueError("saved signal chart-bar cursor is no longer present in intraday archive")
    completed_timestamps = {bar.timestamp.isoformat() for bar in completed_signal_bars}
    vehicle_by_timestamp = {bar.timestamp.isoformat(): bar for bar in vehicle_chart_bars}

    pending = symbol_state.get("pending_signal")
    executed: list[dict[str, Any]] = []
    start_index = index_by_timestamp[last_processed] + 1

    # A signal confirmed on the prior run executes as soon as the next signal
    # bucket exists and the matching vehicle bucket open is available.
    if isinstance(pending, Mapping) and start_index < len(signal_chart_bars):
        fill_timestamp = signal_chart_bars[start_index].timestamp.isoformat()
        fill_bar = vehicle_by_timestamp.get(fill_timestamp)
        if fill_bar is not None:
            event = _event_from_pending(
                symbol=primary.vehicle_symbol,
                strategy_id=primary.strategy_id,
                pending=pending,
                fill_timestamp=fill_timestamp,
                fill_price=fill_bar.open,
                target_notional=_allocation_notional(symbol_state),
            )
            applied = execute_frozen_primary_event(event, config_path=config_path, ledger_dir=ledger_dir)
            executed.append(applied)
            pending = None

    for index in range(start_index, len(signal_chart_bars)):
        bar = signal_chart_bars[index]
        next_timestamp = signal_chart_bars[index + 1].timestamp if index + 1 < len(signal_chart_bars) else None

        stop_event = _process_catastrophic_stop_bucket(
            symbol=primary.vehicle_symbol,
            strategy_id=primary.strategy_id,
            catastrophic_stop_percent=primary.catastrophic_stop_percent,
            bucket_start=bar.timestamp,
            bucket_end=next_timestamp,
            raw_rows=vehicle_raw_rows,
            ledger_dir=ledger_dir,
            config_path=config_path,
            symbol_state=symbol_state,
        )
        if stop_event is not None:
            executed.append(stop_event)
            pending = None

        if bar.timestamp.isoformat() not in completed_timestamps:
            continue

        decision = evaluate_frozen_signal(primary.engine_id, primary.parameters, signal_chart_bars[: index + 1])
        position_open = _has_open_position(ledger_dir, primary.vehicle_symbol)
        desired_side = None
        reason = None
        if position_open and decision.exit_signal:
            desired_side = "SELL"
            reason = "FROZEN_DIRECT_PRIMARY_CONFIRMED_TECHNICAL_EXIT"
        elif not position_open and decision.entry_signal:
            desired_side = "BUY"
            reason = "FROZEN_DIRECT_PRIMARY_CONFIRMED_ENTRY"

        if desired_side is not None:
            if index + 1 < len(signal_chart_bars):
                fill_timestamp = signal_chart_bars[index + 1].timestamp.isoformat()
                fill_bar = vehicle_by_timestamp.get(fill_timestamp)
                if fill_bar is not None:
                    event = FrozenPrimaryExecutionEvent(
                        symbol=primary.vehicle_symbol,
                        strategy_id=primary.strategy_id,
                        side=desired_side,
                        execution_timestamp=fill_timestamp,
                        price=fill_bar.open,
                        reason=reason,
                        target_notional=_allocation_notional(symbol_state) if desired_side == "BUY" else None,
                    )
                    applied = execute_frozen_primary_event(event, config_path=config_path, ledger_dir=ledger_dir)
                    executed.append(applied)
                    pending = None
                else:
                    pending = {
                        "side": desired_side,
                        "signal_chart_bar": bar.timestamp.isoformat(),
                        "reason": reason,
                    }
            else:
                pending = {
                    "side": desired_side,
                    "signal_chart_bar": bar.timestamp.isoformat(),
                    "reason": reason,
                }

        symbol_state["last_processed_chart_bar"] = bar.timestamp.isoformat()

    symbol_state["pending_signal"] = pending
    return {
        **_row(symbol, primary.strategy_id, "PROCESSED"),
        "signal_symbol": primary.signal_symbol,
        "vehicle_symbol": primary.vehicle_symbol,
        "last_processed_chart_bar": symbol_state["last_processed_chart_bar"],
        "last_processed_stop_raw_bar": symbol_state.get("last_processed_stop_raw_bar"),
        "catastrophic_stop_percent": primary.catastrophic_stop_percent,
        "pending_signal": pending,
        "executed_events": executed,
        "state": symbol_state,
    }


def _process_catastrophic_stop_bucket(
    *,
    symbol: str,
    strategy_id: str,
    catastrophic_stop_percent: float | None,
    bucket_start: datetime,
    bucket_end: datetime | None,
    raw_rows: Sequence[IntradayBar],
    ledger_dir: Path,
    config_path: Path,
    symbol_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Process new vehicle raw rows in one chart bucket and apply first stop breach."""
    cursor_text = str(symbol_state.get("last_processed_stop_raw_bar", ""))
    cursor = _parse_timestamp(cursor_text) if cursor_text else None
    candidates = [
        row
        for row in raw_rows
        if row.timestamp >= bucket_start
        and (bucket_end is None or row.timestamp < bucket_end)
        and (cursor is None or row.timestamp > cursor)
    ]
    if not candidates:
        return None

    stop_result: dict[str, Any] | None = None
    if catastrophic_stop_percent is not None and _has_open_position(ledger_dir, symbol):
        entry_price = _open_position_entry_price(ledger_dir, symbol, strategy_id)
        stop_price = entry_price * (1.0 - catastrophic_stop_percent / 100.0)
        for raw in candidates:
            if raw.low <= stop_price:
                event = FrozenPrimaryExecutionEvent(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    side="SELL",
                    execution_timestamp=raw.timestamp.isoformat(),
                    price=stop_price,
                    reason="FROZEN_DIRECT_PRIMARY_CATASTROPHIC_STOP_RAW_INTRADAY",
                )
                stop_result = execute_frozen_primary_event(
                    event,
                    config_path=config_path,
                    ledger_dir=ledger_dir,
                )
                break

    # Cursor advances through all observed vehicle rows in this bucket. When flat
    # this prevents stale lows from becoming eligible after a future re-entry.
    symbol_state["last_processed_stop_raw_bar"] = candidates[-1].timestamp.isoformat()
    return stop_result


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
    current = _open_position(ledger_dir, symbol)
    if current is None:
        return None
    value = float(current.get("cost_basis"))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("open position cost_basis must be positive and finite")
    return value


def _open_position_entry_price(ledger_dir: Path, symbol: str, strategy_id: str) -> float:
    current = _open_position(ledger_dir, symbol)
    if current is None:
        raise ValueError(f"no open paper position for {symbol}")
    if str(current.get("active_strategy", "")).strip().upper() != strategy_id:
        raise ValueError("open paper position is not controlled by the current frozen DIRECT Primary")
    value = float(current.get("entry_price"))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("open position entry_price must be positive and finite")
    return value


def _open_position(ledger_dir: Path, symbol: str) -> dict[str, Any] | None:
    payload = _load_object(ledger_dir / "open_positions.json")
    rows = payload.get("positions")
    if not isinstance(rows, list):
        raise ValueError("open_positions ledger must contain a positions list")
    matches = [dict(row) for row in rows if isinstance(row, Mapping) and str(row.get("symbol", "")).strip().upper() == symbol]
    if len(matches) > 1:
        raise ValueError(f"duplicate open paper position for {symbol}")
    return matches[0] if matches else None


def _has_open_position(ledger_dir: Path, symbol: str) -> bool:
    return _open_position(ledger_dir, symbol) is not None


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("saved raw-stop cursor must be timezone-aware")
    return parsed


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

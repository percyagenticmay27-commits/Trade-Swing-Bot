"""Paper-only runtime for frozen 1H/4H/Daily AI-Suggestions strategies.

This runtime is deliberately separate from the legacy declarative manual-strategy
runner. It preserves frozen engine-specific execution timing, NY-session chart
bars, exact Primary-share shadow sizing, and optional raw-intraday catastrophic
stop monitoring without creating paper positions, orders, brokerage calls, or
capital movement.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .frozen_ai_signal_engines import (
    SUPPORTED_ENGINES,
    evaluate_frozen_signal,
    frozen_engine_execution_timing,
)
from .intraday_chart_bars import IntradayBar, build_chart_bars, load_intraday_csv, regular_session_rows
from .manual_strategy_shadow_runner import _primary_share_quantity

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
PAPER_POSITION_CREATION_ENABLED = False
SHADOW_CAPITAL_RESERVED = False
AUTO_PROMOTION_ENABLED = False
SHADOW_SIZING_BASIS = "PRIMARY_SHARE_QUANTITY"


@dataclass(frozen=True, slots=True)
class FrozenStrategySpec:
    strategy_id: str
    name: str
    signal_symbol: str
    vehicle_symbol: str
    timeframe: str
    engine_id: str
    parameters: Mapping[str, Any]
    catastrophic_stop_percent: float | None = None
    assignment_mode: str = "SHADOW"
    enabled: bool = True
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.strategy_id or self.strategy_id != self.strategy_id.strip().upper():
            raise ValueError("strategy_id must be uppercase and trimmed")
        if not self.signal_symbol or self.signal_symbol != self.signal_symbol.strip().upper():
            raise ValueError("signal_symbol must be uppercase and trimmed")
        if not self.vehicle_symbol or self.vehicle_symbol != self.vehicle_symbol.strip().upper():
            raise ValueError("vehicle_symbol must be uppercase and trimmed")
        if self.timeframe not in {"1H", "4H", "DAILY", "1D"}:
            raise ValueError("frozen strategies currently support 1H, 4H, DAILY, or 1D")
        if self.engine_id not in SUPPORTED_ENGINES:
            raise ValueError(f"unsupported frozen engine: {self.engine_id}")
        if self.assignment_mode not in {"DIRECT", "SHADOW"}:
            raise ValueError("assignment_mode must be DIRECT or SHADOW")
        if self.catastrophic_stop_percent is not None and not (0.0 < self.catastrophic_stop_percent < 100.0):
            raise ValueError("catastrophic_stop_percent must be between 0 and 100")
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")


def _bars_by_timestamp(rows: Sequence[IntradayBar]) -> dict[datetime, IntradayBar]:
    return {row.timestamp: row for row in rows}


def _raw_rows_between(rows: Sequence[IntradayBar], start: datetime, end: datetime) -> list[IntradayBar]:
    return [row for row in rows if start <= row.timestamp < end]


def _chart_timeframe(timeframe: str) -> str:
    """Map assignment vocabulary to the chart-bar builder's frozen vocabulary."""
    return "1D" if timeframe == "DAILY" else timeframe


def simulate_frozen_strategy(
    spec: FrozenStrategySpec,
    signal_rows: Sequence[IntradayBar],
    vehicle_rows: Sequence[IntradayBar],
    *,
    test_quantity: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Simulate one frozen strategy using its authoritative execution timing."""
    if not math.isfinite(test_quantity) or test_quantity <= 0:
        raise ValueError("test_quantity must be a positive finite number")

    execution_timing = frozen_engine_execution_timing(spec.engine_id)
    close_execution = execution_timing == "CONFIRMED_SIGNAL_BAR_CLOSE"
    chart_timeframe = _chart_timeframe(spec.timeframe)
    signal_chart = build_chart_bars(signal_rows, chart_timeframe)  # type: ignore[arg-type]
    vehicle_chart = build_chart_bars(vehicle_rows, chart_timeframe)  # type: ignore[arg-type]
    vehicle_chart_by_ts = _bars_by_timestamp(vehicle_chart)
    vehicle_raw = regular_session_rows(vehicle_rows)

    ledger: list[dict[str, Any]] = []
    position_open = False
    entry_price: float | None = None
    entry_timestamp: datetime | None = None
    pending_entry = False
    pending_exit = False
    realized = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    wins = 0
    losses = 0
    equity_peak = 0.0
    max_drawdown = 0.0

    def close_trade(timestamp: datetime, price: float, reason: str) -> None:
        nonlocal position_open, entry_price, entry_timestamp, realized, gross_profit, gross_loss, wins, losses, pending_exit
        assert entry_price is not None
        trade_pl = (price - entry_price) * test_quantity
        realized += trade_pl
        if trade_pl > 0:
            wins += 1
            gross_profit += trade_pl
        elif trade_pl < 0:
            losses += 1
            gross_loss += trade_pl
        ledger.append({
            "timestamp": timestamp.isoformat(),
            "signal_symbol": spec.signal_symbol,
            "vehicle_symbol": spec.vehicle_symbol,
            "strategy_id": spec.strategy_id,
            "event": "EXIT",
            "exit_reason": reason,
            "vehicle_price": round(price, 6),
            "shares": round(test_quantity, 8),
            "primary_reference_quantity": round(test_quantity, 8),
            "shadow_test_quantity": round(test_quantity, 8),
            "sizing_basis": SHADOW_SIZING_BASIS,
            "realized_pl": round(trade_pl, 2),
            "cumulative_realized_pl": round(realized, 2),
        })
        position_open = False
        entry_price = None
        entry_timestamp = None
        pending_exit = False

    def open_trade(timestamp: datetime, price: float, reason: str) -> None:
        nonlocal position_open, entry_price, entry_timestamp
        entry_price = price
        entry_timestamp = timestamp
        position_open = True
        ledger.append({
            "timestamp": timestamp.isoformat(),
            "signal_symbol": spec.signal_symbol,
            "vehicle_symbol": spec.vehicle_symbol,
            "strategy_id": spec.strategy_id,
            "event": "ENTRY",
            "entry_reason": reason,
            "vehicle_price": round(entry_price, 6),
            "shares": round(test_quantity, 8),
            "simulated_notional": round(entry_price * test_quantity, 2),
            "primary_reference_quantity": round(test_quantity, 8),
            "shadow_test_quantity": round(test_quantity, 8),
            "sizing_basis": SHADOW_SIZING_BASIS,
        })

    for index, signal_bar in enumerate(signal_chart):
        vehicle_bar = vehicle_chart_by_ts.get(signal_bar.timestamp)
        if vehicle_bar is None:
            continue

        if not close_execution:
            if pending_exit and position_open:
                close_trade(signal_bar.timestamp, vehicle_bar.open, "TECHNICAL_NEXT_BAR_OPEN")
            if pending_entry and not position_open:
                open_trade(signal_bar.timestamp, vehicle_bar.open, "CONFIRMED_SIGNAL_NEXT_BAR_OPEN")
            pending_entry = False
            pending_exit = False

        if position_open and entry_price is not None and spec.catastrophic_stop_percent is not None:
            next_timestamp = signal_chart[index + 1].timestamp if index + 1 < len(signal_chart) else datetime.max.replace(tzinfo=signal_bar.timestamp.tzinfo)
            stop_price = entry_price * (1.0 - spec.catastrophic_stop_percent / 100.0)
            for raw in _raw_rows_between(vehicle_raw, signal_bar.timestamp, next_timestamp):
                if raw.low <= stop_price:
                    close_trade(raw.timestamp, stop_price, "CATASTROPHIC_STOP_RAW_INTRADAY")
                    break

        decision = evaluate_frozen_signal(spec.engine_id, spec.parameters, signal_chart[: index + 1])
        if close_execution:
            if position_open and decision.exit_signal:
                close_trade(signal_bar.timestamp, vehicle_bar.close, "TECHNICAL_CONFIRMED_BAR_CLOSE")
            elif not position_open and decision.entry_signal:
                open_trade(signal_bar.timestamp, vehicle_bar.close, "CONFIRMED_SIGNAL_BAR_CLOSE")
        else:
            if position_open and decision.exit_signal:
                pending_exit = True
            elif not position_open and decision.entry_signal:
                pending_entry = True

        current_price = vehicle_bar.close
        open_pl = 0.0 if not position_open or entry_price is None else (current_price - entry_price) * test_quantity
        equity = realized + open_pl
        equity_peak = max(equity_peak, equity)
        max_drawdown = min(max_drawdown, equity - equity_peak)

    final_open_pl = 0.0
    if position_open and entry_price is not None and vehicle_chart:
        final_open_pl = (vehicle_chart[-1].close - entry_price) * test_quantity
    net_pl = realized + final_open_pl
    closed = wins + losses
    profit_factor = None if gross_loss == 0 else gross_profit / abs(gross_loss)
    performance = {
        "evidence_status": "AVAILABLE",
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.name,
        "signal_symbol": spec.signal_symbol,
        "vehicle_symbol": spec.vehicle_symbol,
        "timeframe": spec.timeframe,
        "engine_id": spec.engine_id,
        "trade_count": closed,
        "wins": wins,
        "losses": losses,
        "win_rate": None if closed == 0 else round(wins / closed * 100.0, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "realized_pl": round(realized, 2),
        "open_pl": round(final_open_pl, 2),
        "net_pl": round(net_pl, 2),
        "max_drawdown": round(max_drawdown, 2),
        "profit_factor": None if profit_factor is None else round(profit_factor, 4),
        "open_position": position_open,
        "primary_reference_quantity": round(test_quantity, 8),
        "shadow_test_quantity": round(test_quantity, 8),
        "sizing_basis": SHADOW_SIZING_BASIS,
        "execution_timing": execution_timing,
        "catastrophic_stop_percent": spec.catastrophic_stop_percent,
        "catastrophic_stop_authority": "RAW_INTRADAY_VEHICLE_ROWS" if spec.catastrophic_stop_percent is not None else None,
        "promotion_recommended": False,
        "promotion_recommendation_status": "NOT_EVALUATED_BY_FROZEN_RUNTIME",
    }
    return ledger, performance


def run_frozen_shadow_spec(
    spec: FrozenStrategySpec,
    *,
    signal_intraday_path: Path,
    vehicle_intraday_path: Path,
    primary_positions_path: Path,
    source_timezone: str = "America/New_York",
) -> dict[str, Any]:
    """Load authoritative inputs, resolve exact Primary shares, and simulate."""
    if not spec.enabled:
        return {"evidence_status": "DISABLED", "strategy_id": spec.strategy_id}
    if not signal_intraday_path.is_file() or not vehicle_intraday_path.is_file():
        return {"evidence_status": "MISSING_INTRADAY_MARKET_DATA", "strategy_id": spec.strategy_id}
    try:
        quantity = _primary_share_quantity(primary_positions_path, spec.vehicle_symbol)
    except (OSError, ValueError, TypeError) as exc:
        return {"evidence_status": "PRIMARY_SHARE_QUANTITY_ERROR", "strategy_id": spec.strategy_id, "error": f"{type(exc).__name__}: {exc}"}
    if quantity is None:
        return {"evidence_status": "MISSING_PRIMARY_SHARE_QUANTITY", "strategy_id": spec.strategy_id}
    try:
        signal_rows = load_intraday_csv(signal_intraday_path, source_timezone=source_timezone)
        vehicle_rows = load_intraday_csv(vehicle_intraday_path, source_timezone=source_timezone)
        ledger, performance = simulate_frozen_strategy(spec, signal_rows, vehicle_rows, test_quantity=quantity)
    except (OSError, ValueError, TypeError) as exc:
        return {"evidence_status": "EVIDENCE_ERROR", "strategy_id": spec.strategy_id, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "schema_version": "1.0",
        "paper_trade_mode": True,
        "shadow_allocation_model": "SAME_PRIMARY_SHARE_QUANTITY_SIMULATED_ONLY",
        "shadow_sizing_basis": SHADOW_SIZING_BASIS,
        "signal_price_authority": "NY_RTH_INTRADAY_SIGNAL_SYMBOL",
        "pnl_price_authority": "NY_RTH_INTRADAY_VEHICLE_SYMBOL",
        "primary_quantity_authority": str(primary_positions_path),
        "capital_movement_enabled": False,
        "paper_positions_created": 0,
        "auto_promotion_enabled": False,
        "ledger_rows": ledger,
        "performance": performance,
    }

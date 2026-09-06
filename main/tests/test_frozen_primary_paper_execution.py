import json
from pathlib import Path

import pytest

from swing_trade_bot.frozen_primary_paper_execution import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    SHADOW_EXECUTION_ENABLED,
    FrozenPrimaryExecutionEvent,
    execute_frozen_primary_event,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _config(path: Path) -> None:
    _write_json(
        path,
        {
            "schema_version": "1.0",
            "paper_trade_mode": True,
            "strategy_id": "SWING-001",
            "symbols": [
                {
                    "symbol": "SOXL",
                    "primary_strategy_id": "SOXL_PRIMARY",
                    "shadow_strategy_ids": ["SOXL_SHADOW"],
                    "shadow_slot_3": None,
                }
            ],
            "strategies": [
                {
                    "strategy_id": "SOXL_PRIMARY",
                    "name": "Primary",
                    "signal_symbol": "SOXL",
                    "vehicle_symbol": "SOXL",
                    "timeframe": "1H",
                    "engine_id": "BIGBELUGA_RANGE",
                    "parameters": {"hma_entry": 0, "hma_exit": 90},
                    "catastrophic_stop_percent": 20.0,
                    "assignment_mode": "DIRECT",
                    "enabled": True,
                    "paper_trade_mode": True,
                },
                {
                    "strategy_id": "SOXL_SHADOW",
                    "name": "Shadow",
                    "signal_symbol": "SOXL",
                    "vehicle_symbol": "SOXL",
                    "timeframe": "1H",
                    "engine_id": "ZERO_LAG",
                    "parameters": {"length": 70, "multiplier": 2.5},
                    "catastrophic_stop_percent": 20.0,
                    "assignment_mode": "SHADOW",
                    "enabled": True,
                    "paper_trade_mode": True,
                },
            ],
        },
    )


def _ledger(root: Path, *, with_position: bool = True) -> Path:
    ledger = root / "ledger"
    positions = []
    if with_position:
        positions.append(
            {
                "symbol": "SOXL",
                "entry_date": "2026-08-01",
                "entry_price": 100.0,
                "shares": 10.0,
                "cost_basis": 1000.0,
                "current_price": 110.0,
                "market_value": 1100.0,
                "unrealized_pnl": 100.0,
                "unrealized_pnl_percent": 10.0,
                "allocation_percent": 25.0,
                "active_strategy": "SOXL_PRIMARY",
                "status": "OPEN",
            }
        )
    _write_json(ledger / "open_positions.json", {"paper_trade_mode": True, "positions": positions})
    _write_json(
        ledger / "trade_history.json",
        {
            "paper_trade_mode": True,
            "trades": [
                {
                    "trade_id": "ORIGINAL-BUY",
                    "symbol": "SOXL",
                    "side": "BUY",
                    "trade_date": "2026-08-01",
                    "price": 100.0,
                    "shares": 10.0,
                    "notional": 1000.0,
                    "active_strategy": "SOXL_PRIMARY",
                    "reason": "ORIGINAL",
                    "paper_trade_mode": True,
                }
            ] if with_position else [],
        },
    )
    return ledger


def test_direct_primary_can_close_existing_paper_position(tmp_path):
    config = tmp_path / "config.json"
    _config(config)
    ledger = _ledger(tmp_path)
    event = FrozenPrimaryExecutionEvent(
        symbol="SOXL",
        strategy_id="SOXL_PRIMARY",
        side="SELL",
        execution_timestamp="2026-09-03T10:30:00-04:00",
        price=120.0,
        reason="TECHNICAL_NEXT_BAR_OPEN",
    )

    result = execute_frozen_primary_event(event, config_path=config, ledger_dir=ledger)

    assert result["status"] == "PAPER_POSITION_CLOSED"
    assert result["shares"] == 10.0
    assert result["notional"] == 1200.0
    positions = json.loads((ledger / "open_positions.json").read_text())["positions"]
    trades = json.loads((ledger / "trade_history.json").read_text())["trades"]
    assert positions == []
    assert trades[-1]["side"] == "SELL"
    assert trades[-1]["active_strategy"] == "SOXL_PRIMARY"
    assert trades[-1]["execution_authority"] == "FROZEN_DIRECT_PRIMARY"


def test_direct_primary_can_reenter_with_explicit_target_notional(tmp_path):
    config = tmp_path / "config.json"
    _config(config)
    ledger = _ledger(tmp_path, with_position=False)
    event = FrozenPrimaryExecutionEvent(
        symbol="SOXL",
        strategy_id="SOXL_PRIMARY",
        side="BUY",
        execution_timestamp="2026-09-04T09:30:00-04:00",
        price=125.0,
        target_notional=1000.0,
        reason="CONFIRMED_SIGNAL_NEXT_BAR_OPEN",
    )

    result = execute_frozen_primary_event(event, config_path=config, ledger_dir=ledger)

    assert result["status"] == "PAPER_POSITION_OPENED"
    assert result["shares"] == 8.0
    position = json.loads((ledger / "open_positions.json").read_text())["positions"][0]
    assert position["shares"] == 8.0
    assert position["cost_basis"] == 1000.0
    assert position["active_strategy"] == "SOXL_PRIMARY"


def test_shadow_strategy_is_rejected_from_paper_execution(tmp_path):
    config = tmp_path / "config.json"
    _config(config)
    ledger = _ledger(tmp_path)
    event = FrozenPrimaryExecutionEvent(
        symbol="SOXL",
        strategy_id="SOXL_SHADOW",
        side="SELL",
        execution_timestamp="2026-09-03T10:30:00-04:00",
        price=120.0,
        reason="SHADOW_SIGNAL",
    )

    with pytest.raises(ValueError, match="only the current frozen DIRECT Primary"):
        execute_frozen_primary_event(event, config_path=config, ledger_dir=ledger)

    assert len(json.loads((ledger / "open_positions.json").read_text())["positions"]) == 1


def test_execution_is_idempotent_by_deterministic_trade_id(tmp_path):
    config = tmp_path / "config.json"
    _config(config)
    ledger = _ledger(tmp_path)
    event = FrozenPrimaryExecutionEvent(
        symbol="SOXL",
        strategy_id="SOXL_PRIMARY",
        side="SELL",
        execution_timestamp="2026-09-03T10:30:00-04:00",
        price=120.0,
        reason="TECHNICAL_NEXT_BAR_OPEN",
    )

    first = execute_frozen_primary_event(event, config_path=config, ledger_dir=ledger)
    second = execute_frozen_primary_event(event, config_path=config, ledger_dir=ledger)

    assert first["trade_id"] == second["trade_id"]
    assert second["status"] == "ALREADY_APPLIED"
    trades = json.loads((ledger / "trade_history.json").read_text())["trades"]
    assert sum(row["trade_id"] == first["trade_id"] for row in trades) == 1


def test_buy_requires_target_notional_and_cannot_double_open(tmp_path):
    config = tmp_path / "config.json"
    _config(config)
    ledger = _ledger(tmp_path, with_position=False)
    missing_notional = FrozenPrimaryExecutionEvent(
        symbol="SOXL",
        strategy_id="SOXL_PRIMARY",
        side="BUY",
        execution_timestamp="2026-09-04T09:30:00-04:00",
        price=125.0,
        reason="ENTRY",
    )
    with pytest.raises(ValueError, match="BUY requires target_notional"):
        execute_frozen_primary_event(missing_notional, config_path=config, ledger_dir=ledger)

    valid = FrozenPrimaryExecutionEvent(
        symbol="SOXL",
        strategy_id="SOXL_PRIMARY",
        side="BUY",
        execution_timestamp="2026-09-04T09:30:00-04:00",
        price=125.0,
        target_notional=1000.0,
        reason="ENTRY",
    )
    execute_frozen_primary_event(valid, config_path=config, ledger_dir=ledger)
    later = FrozenPrimaryExecutionEvent(
        symbol="SOXL",
        strategy_id="SOXL_PRIMARY",
        side="BUY",
        execution_timestamp="2026-09-04T10:30:00-04:00",
        price=126.0,
        target_notional=1000.0,
        reason="ENTRY_AGAIN",
    )
    with pytest.raises(ValueError, match="paper position already open"):
        execute_frozen_primary_event(later, config_path=config, ledger_dir=ledger)


def test_safety_flags_are_locked_and_no_broker_execution_surface_exists():
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert SHADOW_EXECUTION_ENABLED is False
    source = Path("src/swing_trade_bot/frozen_primary_paper_execution.py").read_text(encoding="utf-8").lower()
    assert "robin_stocks" not in source
    assert "place_order" not in source

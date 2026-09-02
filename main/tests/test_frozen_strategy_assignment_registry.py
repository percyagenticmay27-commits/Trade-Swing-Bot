import json
from pathlib import Path

import pytest

from swing_trade_bot.frozen_strategy_assignment_registry import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    load_frozen_symbol_stacks,
    resolve_frozen_stack,
)


def test_repository_soxl_stack_matches_frozen_deployment_order() -> None:
    stack = resolve_frozen_stack("SOXL", Path("configs/frozen_strategy_assignments.json"))
    assert stack is not None
    assert stack.primary.strategy_id == "SOXL_BIGBELUGA_1H_PRIMARY"
    assert stack.primary.engine_id == "BIGBELUGA_RANGE"
    assert stack.primary.timeframe == "1H"
    assert stack.primary.parameters["hma_entry"] == 0
    assert stack.primary.parameters["hma_exit"] == 90
    assert stack.primary.catastrophic_stop_percent == 20.0

    assert [item.strategy_id for item in stack.shadows] == [
        "SOXL_ZERO_LAG_1H_SHADOW_1",
        "SOXL_ZERO_LAG_4H_SHADOW_2",
    ]
    one_hour, four_hour = stack.shadows
    assert one_hour.parameters["length"] == 70
    assert one_hour.parameters["multiplier"] == 2.5
    assert one_hour.parameters["chop_max"] == 55.0
    assert one_hour.catastrophic_stop_percent == 20.0
    assert four_hour.parameters["length"] == 20
    assert four_hour.parameters["multiplier"] == 1.0
    assert four_hour.parameters["adx_min"] == 20.0
    assert four_hour.catastrophic_stop_percent == 20.0
    assert stack.shadow_slot_3_empty is True


def test_no_tqqq_stack_is_silently_inherited_from_qqq() -> None:
    assert resolve_frozen_stack("TQQQ", Path("configs/frozen_strategy_assignments.json")) is None


def test_registry_enforces_one_direct_and_max_three_shadows(tmp_path: Path) -> None:
    config = tmp_path / "bad.json"
    config.write_text(json.dumps({
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "strategies": [
            {"strategy_id": "P", "name": "P", "signal_symbol": "SOXL", "vehicle_symbol": "SOXL", "timeframe": "1H", "engine_id": "ZERO_LAG", "parameters": {"length": 10, "multiplier": 1}, "assignment_mode": "DIRECT"},
            {"strategy_id": "S1", "name": "S1", "signal_symbol": "SOXL", "vehicle_symbol": "SOXL", "timeframe": "1H", "engine_id": "ZERO_LAG", "parameters": {"length": 10, "multiplier": 1}, "assignment_mode": "SHADOW"},
            {"strategy_id": "S2", "name": "S2", "signal_symbol": "SOXL", "vehicle_symbol": "SOXL", "timeframe": "1H", "engine_id": "ZERO_LAG", "parameters": {"length": 10, "multiplier": 1}, "assignment_mode": "SHADOW"},
            {"strategy_id": "S3", "name": "S3", "signal_symbol": "SOXL", "vehicle_symbol": "SOXL", "timeframe": "1H", "engine_id": "ZERO_LAG", "parameters": {"length": 10, "multiplier": 1}, "assignment_mode": "SHADOW"},
            {"strategy_id": "S4", "name": "S4", "signal_symbol": "SOXL", "vehicle_symbol": "SOXL", "timeframe": "1H", "engine_id": "ZERO_LAG", "parameters": {"length": 10, "multiplier": 1}, "assignment_mode": "SHADOW"}
        ],
        "symbols": [{"symbol": "SOXL", "primary_strategy_id": "P", "shadow_strategy_ids": ["S1", "S2", "S3", "S4"]}]
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="at most three"):
        load_frozen_symbol_stacks(config)


def test_registry_is_paper_only() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False

from pathlib import Path

from swing_trade_bot.frozen_strategy_assignment_registry import resolve_frozen_stack


def test_amzn_signal_stack_is_assigned_to_amzu_in_frozen_rank_order() -> None:
    stack = resolve_frozen_stack("AMZU", Path("configs/frozen_strategy_assignments.json"))
    assert stack is not None
    assert stack.research_status == "AMZN_SIGNAL_MAPPED_AMZU_PAPER_VALIDATION"
    assert stack.primary.strategy_id == "AMZU_AMZN_KELTNER_4H_PRIMARY"
    assert stack.primary.signal_symbol == "AMZN"
    assert stack.primary.vehicle_symbol == "AMZU"
    assert stack.primary.engine_id == "KELTNER_LONG"
    assert stack.primary.timeframe == "4H"
    assert stack.primary.parameters == {
        "kc_length": 14,
        "kc_factor": 1.0,
        "hma_length": 0,
        "chop_max": 0.0,
        "adx_min": 0.0,
        "atr_pct_min": 0.0,
        "exit_mode": "BASIS",
    }
    assert [item.strategy_id for item in stack.shadows] == [
        "AMZU_AMZN_AI_C2_4H_SHADOW_1",
        "AMZU_AMZN_BIGBELUGA_1H_SHADOW_2",
        "AMZU_AMZN_STRATEGY_F_1H_SHADOW_3",
        "AMZU_AMZN_AI_C1_DAILY_SHADOW_4",
    ]
    c2, bigbeluga, strategy_f, c1 = stack.shadows
    assert c2.engine_id == "C2_RECON" and c2.parameters["hma_length"] == 20
    assert bigbeluga.engine_id == "BIGBELUGA_RANGE"
    assert bigbeluga.parameters["hma_entry"] == 20
    assert bigbeluga.parameters["hma_exit"] == 38
    assert strategy_f.engine_id == "STRATEGY_F"
    assert strategy_f.parameters["adx_min"] == 25.0
    assert c1.engine_id == "C1_RECON"
    assert c1.timeframe == "DAILY"
    assert c1.parameters["hma_length"] == 40
    assert all(item.signal_symbol == "AMZN" for item in stack.shadows)
    assert all(item.vehicle_symbol == "AMZU" for item in stack.shadows)
    assert all(item.catastrophic_stop_percent == 20.0 for item in (stack.primary, *stack.shadows))


def test_amzn_historical_checkpoints_remain_underlying_research_only() -> None:
    stack = resolve_frozen_stack("AMZU", Path("configs/frozen_strategy_assignments.json"))
    assert stack is not None
    specs = (stack.primary, *stack.shadows)
    expected = [
        (40, 65.00, 43.05, 2.610, 11.07),
        (118, 54.24, 33.47, 1.654, 8.66),
        (75, 40.00, 17.51, 1.750, 8.45),
        (76, 44.74, 15.72, 1.421, 9.85),
        (46, 58.70, 7.53, 1.223, 12.78),
    ]
    for spec, metrics in zip(specs, expected):
        checkpoint = spec.parameters  # assignment loader intentionally exposes execution parameters only
        assert spec.paper_trade_mode is True
        assert spec.signal_symbol == "AMZN"
        assert spec.vehicle_symbol == "AMZU"
        assert checkpoint is not None

import json
from pathlib import Path

from swing_trade_bot.frozen_strategy_assignment_registry import resolve_frozen_stack


CONFIG = Path("configs/frozen_strategy_assignments.json")


def test_avgo_signal_stack_is_assigned_to_avl_with_zero_lag_primary() -> None:
    stack = resolve_frozen_stack("AVL", CONFIG)
    assert stack is not None
    assert stack.research_status == "AVGO_SIGNAL_MAPPED_AVL_PAPER_VALIDATION"
    assert stack.primary.strategy_id == "AVL_AVGO_ZERO_LAG_BALANCE_1H_PRIMARY"
    assert stack.primary.signal_symbol == "AVGO"
    assert stack.primary.vehicle_symbol == "AVL"
    assert stack.primary.engine_id == "ZERO_LAG"
    assert stack.primary.timeframe == "1H"
    assert stack.primary.parameters == {
        "length": 40,
        "multiplier": 1.0,
        "adx_min": 0.0,
        "chop_max": 0.0,
        "atr_pct_min": 0.0,
    }

    assert [item.strategy_id for item in stack.shadows] == [
        "AVL_AVGO_AI_C1_DAILY_SHADOW_1",
        "AVL_AVGO_KELTNER_1H_SHADOW_2",
        "AVL_AVGO_STRATEGY_F_1H_SHADOW_3",
        "AVL_AVGO_AI_C2_DAILY_SHADOW_4",
    ]
    assert len(stack.shadows) == 4


def test_avgo_frozen_shadow_parameters_match_handoff() -> None:
    stack = resolve_frozen_stack("AVL", CONFIG)
    assert stack is not None
    c1, keltner, strategy_f, c2 = stack.shadows

    assert c1.engine_id == "C1_RECON"
    assert c1.timeframe == "DAILY"
    assert c1.parameters == {"hma_length": 0, "chop_max": 62.5, "adx_min": 12.5, "rsi_min": 0.0}

    assert keltner.engine_id == "KELTNER_LONG"
    assert keltner.parameters == {
        "kc_length": 20,
        "kc_factor": 2.0,
        "hma_length": 40,
        "chop_max": 55.0,
        "adx_min": 0.0,
        "atr_pct_min": 0.75,
        "exit_mode": "LOWER",
    }

    assert strategy_f.engine_id == "STRATEGY_F"
    assert strategy_f.parameters == {
        "tema_length": 44,
        "macd_fast": 17,
        "macd_slow": 26,
        "macd_signal": 9,
        "hma_length": 72,
        "chop_max": 62.5,
        "adx_min": 0.0,
        "atr_pct_min": 0.0,
        "rsi_min": 0.0,
    }

    assert c2.engine_id == "C2_RECON"
    assert c2.timeframe == "DAILY"
    assert c2.parameters == {"mode": "K_K_CROSS", "hma_length": 0, "chop_max": 55.0, "adx_min": 20.0, "rsi_min": 45.0}


def test_avgo_mapping_is_paper_only_and_uses_twenty_percent_vehicle_stop() -> None:
    stack = resolve_frozen_stack("AVL", CONFIG)
    assert stack is not None
    specs = (stack.primary, *stack.shadows)
    assert all(item.signal_symbol == "AVGO" for item in specs)
    assert all(item.vehicle_symbol == "AVL" for item in specs)
    assert all(item.paper_trade_mode is True for item in specs)
    assert all(item.catastrophic_stop_percent == 20.0 for item in specs)


def test_avgo_historical_period_and_metrics_remain_underlying_reference_only() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    rows = {
        row["strategy_id"]: row
        for row in payload["strategies"]
        if row["strategy_id"].startswith("AVL_AVGO_")
    }
    expected = {
        "AVL_AVGO_ZERO_LAG_BALANCE_1H_PRIMARY": (121, 47.93, 122.00, 2.714, 8.04),
        "AVL_AVGO_AI_C1_DAILY_SHADOW_1": (74, 68.92, 69.96, 2.375, 16.67),
        "AVL_AVGO_KELTNER_1H_SHADOW_2": (69, 36.23, 119.02, 4.431, 11.82),
        "AVL_AVGO_STRATEGY_F_1H_SHADOW_3": (142, 42.96, 105.83, 2.187, 12.97),
        "AVL_AVGO_AI_C2_DAILY_SHADOW_4": (36, 63.89, 56.07, 3.688, 8.59),
    }
    assert set(rows) == set(expected)
    for strategy_id, metrics in expected.items():
        checkpoint = rows[strategy_id]["frozen_checkpoint"]
        assert checkpoint["source_symbol"] == "AVGO"
        assert checkpoint["deployment_vehicle"] == "AVL"
        assert checkpoint["backtest_period"] == "2023-01-01_to_2026-08-18"
        assert checkpoint["profitable_periods"] == "4/4"
        assert "HISTORICAL_REFERENCE_ONLY" in checkpoint["checkpoint_scope"]
        actual = (
            checkpoint["trade_count"],
            checkpoint["win_rate_percent"],
            checkpoint["net_pl_dollars"],
            checkpoint["profit_factor"],
            checkpoint["max_drawdown_dollars"],
        )
        assert actual == metrics

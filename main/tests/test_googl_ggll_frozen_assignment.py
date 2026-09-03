from pathlib import Path

from swing_trade_bot.frozen_strategy_assignment_registry import resolve_frozen_stack


def test_googl_signal_stack_is_assigned_to_ggll_with_strategy_f_primary() -> None:
    stack = resolve_frozen_stack("GGLL", Path("configs/frozen_strategy_assignments.json"))
    assert stack is not None
    assert stack.research_status == "GOOGL_SIGNAL_MAPPED_GGLL_PAPER_VALIDATION"
    assert stack.primary.strategy_id == "GGLL_GOOG_STRATEGY_F_1H_PRIMARY"
    assert stack.primary.signal_symbol == "GOOGL"
    assert stack.primary.vehicle_symbol == "GGLL"
    assert stack.primary.engine_id == "STRATEGY_F"
    assert stack.primary.timeframe == "1H"
    assert stack.primary.parameters == {
        "tema_length": 44,
        "macd_fast": 17,
        "macd_slow": 26,
        "macd_signal": 9,
        "hma_length": 10,
        "chop_max": 50.0,
        "adx_min": 0.0,
        "atr_pct_min": 0.0,
        "rsi_min": 0.0,
    }

    assert [item.strategy_id for item in stack.shadows] == [
        "GGLL_GOOG_ZERO_LAG_1H_SHADOW_1",
        "GGLL_GOOG_ZERO_LAG_4H_SHADOW_2",
        "GGLL_GOOG_AI_C2_4H_SHADOW_3",
    ]

    zero_lag_1h, zero_lag_4h, c2 = stack.shadows
    assert zero_lag_1h.engine_id == "ZERO_LAG"
    assert zero_lag_1h.parameters["length"] == 30
    assert zero_lag_1h.parameters["multiplier"] == 2.5
    assert zero_lag_1h.parameters["adx_min"] == 20.0

    assert zero_lag_4h.engine_id == "ZERO_LAG"
    assert zero_lag_4h.timeframe == "4H"
    assert zero_lag_4h.parameters["length"] == 30
    assert zero_lag_4h.parameters["multiplier"] == 2.0
    assert zero_lag_4h.parameters["adx_min"] == 0.0

    assert c2.engine_id == "C2_RECON"
    assert c2.timeframe == "4H"
    assert c2.parameters["mode"] == "BOTH_BULLISH"
    assert c2.parameters["adx_min"] == 20.0

    specs = (stack.primary, *stack.shadows)
    assert all(item.signal_symbol == "GOOGL" for item in specs)
    assert all(item.vehicle_symbol == "GGLL" for item in specs)
    assert all(item.catastrophic_stop_percent == 20.0 for item in specs)
    assert len(stack.shadows) == 3


def test_googl_historical_period_and_metrics_remain_underlying_reference_only() -> None:
    import json

    payload = json.loads(Path("configs/frozen_strategy_assignments.json").read_text(encoding="utf-8"))
    rows = {
        row["strategy_id"]: row
        for row in payload["strategies"]
        if row["strategy_id"].startswith("GGLL_GOOG_")
    }
    expected = {
        "GGLL_GOOG_STRATEGY_F_1H_PRIMARY": (94, 50.00, 112.20, 2.641, 16.47),
        "GGLL_GOOG_ZERO_LAG_1H_SHADOW_1": (29, 58.62, 135.79, 3.974, 13.05),
        "GGLL_GOOG_ZERO_LAG_4H_SHADOW_2": (15, 80.00, 114.36, 10.977, 5.84),
        "GGLL_GOOG_AI_C2_4H_SHADOW_3": (104, 48.08, 64.22, 1.647, 15.74),
    }
    assert set(rows) == set(expected)
    for strategy_id, metrics in expected.items():
        checkpoint = rows[strategy_id]["frozen_checkpoint"]
        assert checkpoint["source_symbol"] == "GOOGL"
        assert checkpoint["deployment_vehicle"] == "GGLL"
        assert checkpoint["backtest_period"] == "2023-01-01_to_2026-08-18"
        assert "HISTORICAL_REFERENCE_ONLY" in checkpoint["checkpoint_scope"]
        actual = (
            checkpoint["trade_count"],
            checkpoint["win_rate_percent"],
            checkpoint["net_pl_dollars"],
            checkpoint["profit_factor"],
            checkpoint["max_drawdown_dollars"],
        )
        assert actual == metrics

from datetime import date, timedelta
from pathlib import Path

import pytest

from swing_trade_bot.frozen_ai_signal_engines import frozen_engine_execution_timing
from swing_trade_bot.frozen_keltner_engine import evaluate_keltner_long
from swing_trade_bot.frozen_strategy_assignment_registry import resolve_frozen_stack
from swing_trade_bot.frozen_strategy_f_engine import evaluate_strategy_f
from swing_trade_bot.position_state import MarketBar


ASSIGNMENTS = Path("configs/frozen_strategy_assignments.json")
BACKTEST_PERIOD = "2023-01-01_to_2026-08-28"


def _bars(count: int = 120) -> list[MarketBar]:
    start = date(2026, 1, 2)
    bars: list[MarketBar] = []
    for index in range(count):
        close = 100.0 + index * 0.25
        bars.append(
            MarketBar(
                date=start + timedelta(days=index),
                open=close - 0.10,
                high=close + 0.60,
                low=close - 0.60,
                close=close,
                volume=1_000_000.0 + index,
            )
        )
    return bars


def test_repository_nvdx_stack_matches_frozen_nvda_assignment() -> None:
    stack = resolve_frozen_stack("NVDX", ASSIGNMENTS)
    assert stack is not None
    assert stack.research_status == "NVDA_SIGNAL_MAPPED_NVDX_PAPER_VALIDATION"
    assert stack.primary.strategy_id == "NVDX_NVDA_STRATEGY_F_1H_PRIMARY"
    assert stack.primary.signal_symbol == "NVDA"
    assert stack.primary.vehicle_symbol == "NVDX"
    assert stack.primary.engine_id == "STRATEGY_F"
    assert stack.primary.timeframe == "1H"
    assert stack.primary.catastrophic_stop_percent == 20.0
    assert stack.primary.frozen_checkpoint["backtest_period"] == BACKTEST_PERIOD

    assert [item.strategy_id for item in stack.shadows] == [
        "NVDX_NVDA_ZERO_LAG_BALANCE_1H_SHADOW_1",
        "NVDX_NVDA_KELTNER_1H_SHADOW_2",
        "NVDX_NVDA_ZERO_LAG_PROFIT_1H_SHADOW_3",
    ]
    assert all(item.signal_symbol == "NVDA" for item in stack.shadows)
    assert all(item.vehicle_symbol == "NVDX" for item in stack.shadows)
    assert all(item.catastrophic_stop_percent == 20.0 for item in stack.shadows)
    assert all(item.frozen_checkpoint["backtest_period"] == BACKTEST_PERIOD for item in stack.shadows)


def test_nvda_strategy_f_primary_parameters_and_execution_timing_are_exact() -> None:
    stack = resolve_frozen_stack("NVDX", ASSIGNMENTS)
    assert stack is not None
    params = stack.primary.parameters
    assert params["tema_length"] == 44
    assert params["macd_fast"] == 17
    assert params["macd_slow"] == 26
    assert params["macd_signal"] == 9
    assert params["hma_length"] == 72
    assert params["chop_max"] == 0.0
    assert frozen_engine_execution_timing("STRATEGY_F") == "CONFIRMED_SIGNAL_BAR_CLOSE"

    _, _, diagnostics = evaluate_strategy_f(params, _bars())
    assert diagnostics["tema_length"] == 44
    assert diagnostics["macd_fast"] == 17
    assert diagnostics["macd_slow"] == 26
    assert diagnostics["macd_signal_length"] == 9


def test_strategy_f_honors_explicit_indicator_parameters() -> None:
    params = {
        "tema_length": 30,
        "macd_fast": 8,
        "macd_slow": 21,
        "macd_signal": 5,
        "hma_length": 0,
        "chop_max": 0.0,
        "adx_min": 0.0,
        "rsi_min": 0.0,
    }
    _, _, diagnostics = evaluate_strategy_f(params, _bars())
    assert diagnostics["tema_length"] == 30
    assert diagnostics["macd_fast"] == 8
    assert diagnostics["macd_slow"] == 21
    assert diagnostics["macd_signal_length"] == 5


def test_nvda_zero_lag_shadow_specs_are_exact() -> None:
    stack = resolve_frozen_stack("NVDX", ASSIGNMENTS)
    assert stack is not None
    balance, _, profit = stack.shadows

    assert balance.engine_id == "ZERO_LAG"
    assert balance.parameters["length"] == 20
    assert balance.parameters["multiplier"] == 2.0
    assert balance.parameters["adx_min"] == 20.0

    assert profit.engine_id == "ZERO_LAG"
    assert profit.parameters["length"] == 20
    assert profit.parameters["multiplier"] == 2.5
    assert profit.parameters["adx_min"] == 0.0
    assert profit.parameters["chop_max"] == 0.0
    assert profit.parameters["atr_pct_min"] == 0.0

    assert frozen_engine_execution_timing("ZERO_LAG") == "CONFIRMED_SIGNAL_NEXT_CHART_BAR_OPEN"


def test_nvda_keltner_armed_lower_exit_mode_is_supported() -> None:
    stack = resolve_frozen_stack("NVDX", ASSIGNMENTS)
    assert stack is not None
    keltner = stack.shadows[1]
    assert keltner.engine_id == "KELTNER_LONG"
    assert keltner.parameters["kc_length"] == 14
    assert keltner.parameters["kc_factor"] == 1.0
    assert keltner.parameters["hma_length"] == 72
    assert keltner.parameters["chop_max"] == 60.0
    assert keltner.parameters["exit_mode"] == "LOWER_AFTER_UPPER_ARM"
    assert frozen_engine_execution_timing("KELTNER_LONG") == "CONFIRMED_SIGNAL_NEXT_CHART_BAR_OPEN"

    entry, exit_, diagnostics = evaluate_keltner_long(keltner.parameters, _bars())
    assert isinstance(entry, bool)
    assert isinstance(exit_, bool)
    assert diagnostics["ready"] is True


def test_keltner_unknown_exit_mode_fails_closed() -> None:
    with pytest.raises(ValueError, match="LOWER_AFTER_UPPER_ARM"):
        evaluate_keltner_long(
            {"kc_length": 14, "kc_factor": 1.0, "exit_mode": "UNKNOWN"},
            _bars(),
        )

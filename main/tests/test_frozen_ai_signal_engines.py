from datetime import date, timedelta

import pytest

from swing_trade_bot.frozen_ai_signal_engines import SUPPORTED_ENGINES, evaluate_frozen_signal
from swing_trade_bot.position_state import MarketBar


def _bar(index: int, close: float, *, high: float | None = None, low: float | None = None) -> MarketBar:
    return MarketBar(
        date=date(2025, 1, 1) + timedelta(days=index),
        open=close,
        high=close + 1.0 if high is None else high,
        low=close - 1.0 if low is None else low,
        close=close,
        volume=1000.0,
    )


def test_only_recovered_engines_are_exposed() -> None:
    assert SUPPORTED_ENGINES == {"ZERO_LAG", "BIGBELUGA_RANGE"}
    with pytest.raises(ValueError, match="unsupported frozen engine"):
        evaluate_frozen_signal("LOOKALIKE", {}, [_bar(0, 100.0)])


def test_zero_lag_requires_warmup_and_emits_confirmed_transition() -> None:
    # ZERO_LAG needs enough history for the handoff's highest(ATR(length), length*3)
    # volatility window. Use length=10 so the synthetic regression fixture has a
    # realistic 30-bar warmup while remaining compact.
    cold = [_bar(i, 100.0) for i in range(20)]
    assert evaluate_frozen_signal("ZERO_LAG", {"length": 10, "multiplier": 0.1}, cold).diagnostics["ready"] is False

    bars = [_bar(i, 100.0) for i in range(35)]
    bars.append(_bar(35, 120.0, high=121.0, low=119.0))
    decision = evaluate_frozen_signal("ZERO_LAG", {"length": 10, "multiplier": 0.1}, bars)
    assert decision.diagnostics["ready"] is True
    assert decision.diagnostics["large_green"] is True
    assert decision.entry_signal is True
    assert decision.exit_signal is False


def test_zero_lag_chop_filter_can_block_an_entry_transition() -> None:
    bars = [_bar(i, 100.0) for i in range(35)]
    bars.append(_bar(35, 120.0, high=121.0, low=119.0))
    unfiltered = evaluate_frozen_signal("ZERO_LAG", {"length": 10, "multiplier": 0.1}, bars)
    filtered = evaluate_frozen_signal("ZERO_LAG", {"length": 10, "multiplier": 0.1, "chop_max": 0.0001}, bars)
    assert unfiltered.entry_signal is True
    assert filtered.diagnostics["filter_ok"] is False
    assert filtered.entry_signal is False


def test_zero_lag_zero_thresholds_mean_filters_off() -> None:
    bars = [_bar(i, 100.0) for i in range(35)]
    bars.append(_bar(35, 120.0, high=121.0, low=119.0))
    native = evaluate_frozen_signal("ZERO_LAG", {"length": 10, "multiplier": 0.1}, bars)
    explicit_off = evaluate_frozen_signal(
        "ZERO_LAG",
        {
            "length": 10,
            "multiplier": 0.1,
            "adx_min": 0.0,
            "chop_max": 0.0,
            "atr_pct_min": 0.0,
        },
        bars,
    )
    assert explicit_off.diagnostics["filter_ok"] is True
    assert explicit_off.diagnostics["adx"] is None
    assert explicit_off.diagnostics["chop"] is None
    assert explicit_off.diagnostics["atr_pct"] is None
    assert explicit_off.entry_signal == native.entry_signal
    assert explicit_off.exit_signal == native.exit_signal


def test_zero_lag_exposes_current_frozen_band_diagnostics() -> None:
    bars = [_bar(i, 100.0 + i * 0.1) for i in range(40)]
    decision = evaluate_frozen_signal("ZERO_LAG", {"length": 10, "multiplier": 1.0}, bars)
    assert decision.diagnostics["ready"] is True
    assert decision.diagnostics["zlema"] is not None
    assert decision.diagnostics["upper_band"] is not None
    assert decision.diagnostics["lower_band"] is not None
    assert decision.diagnostics["lower_band"] < decision.diagnostics["zlema"] < decision.diagnostics["upper_band"]


def test_bigbeluga_recovered_area_range_green_arrow() -> None:
    bars = [_bar(i, 100.0) for i in range(313)]
    # The recovered Pine initializes the Area Range at bar_index == 301.
    # With a stable 100 center and width near 8, lowerMid is near 96.
    # Bar 311 moves below lowerMid without leaving the range; bar 312 crosses
    # back above it while low[10] remains above lowerMid, creating Green ▲.
    bars[311] = _bar(311, 100.0, high=101.0, low=95.0)
    bars[312] = _bar(312, 100.0, high=101.0, low=97.0)

    decision = evaluate_frozen_signal("BIGBELUGA_RANGE", {"hma_entry": 0, "hma_exit": 90}, bars)
    assert decision.diagnostics["ready"] is True
    assert decision.diagnostics["green_arrow"] is True
    assert decision.entry_signal is True


def test_bigbeluga_zero_thresholds_mean_filters_off() -> None:
    bars = [_bar(i, 100.0) for i in range(313)]
    bars[311] = _bar(311, 100.0, high=101.0, low=95.0)
    bars[312] = _bar(312, 100.0, high=101.0, low=97.0)
    decision = evaluate_frozen_signal(
        "BIGBELUGA_RANGE",
        {"hma_entry": 0, "hma_exit": 0, "chop_max": 0.0, "atr_pct_min": 0.0},
        bars,
    )
    assert decision.diagnostics["filter_ok"] is True
    assert decision.diagnostics["entry_hma"] is None
    assert decision.diagnostics["exit_hma"] is None
    assert decision.diagnostics["chop"] is None
    assert decision.diagnostics["atr_pct"] is None
    assert decision.entry_signal is True


def test_bigbeluga_hma_exit_mode_uses_close_below_hma_instead_of_native_red() -> None:
    bars = [_bar(i, 100.0 + i * 0.02) for i in range(360)]
    bars[-1] = _bar(359, 80.0, high=100.0, low=79.0)
    decision = evaluate_frozen_signal("BIGBELUGA_RANGE", {"hma_exit": 90}, bars)
    assert decision.diagnostics["exit_hma"] is not None
    assert decision.exit_signal is True

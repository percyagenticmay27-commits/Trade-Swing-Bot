"""Authoritative frozen AI-Suggestions signal engines used by Swing research.

This module implements source-recovered mathematics plus the project-authorized
C1/C2 reconstructions preserved in the 2026-09-02 handoff. It is paper/research
logic only and exposes no execution authority.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .frozen_keltner_engine import evaluate_keltner_long
from .frozen_reconstructed_stochastic_engines import evaluate_reconstructed_signal
from .frozen_strategy_f_engine import evaluate_strategy_f
from .frozen_vol_vidya_engine import evaluate_vol_vidya
from .position_state import MarketBar

SUPPORTED_ENGINES = {"ZERO_LAG", "BIGBELUGA_RANGE", "VOL_VIDYA", "KELTNER_LONG", "STRATEGY_F", "C1_RECON", "C2_RECON"}


@dataclass(frozen=True, slots=True)
class FrozenSignalDecision:
    entry_signal: bool
    exit_signal: bool
    engine_id: str
    diagnostics: Mapping[str, float | int | bool | None]


def frozen_engine_execution_timing(engine_id: str) -> str:
    """Return the authoritative execution timing for a frozen engine family."""
    engine = engine_id.strip().upper()
    if engine not in SUPPORTED_ENGINES:
        raise ValueError(f"unsupported frozen engine: {engine_id}")
    return "CONFIRMED_SIGNAL_BAR_CLOSE" if engine == "STRATEGY_F" else "CONFIRMED_SIGNAL_NEXT_CHART_BAR_OPEN"


def _ema_series(values: Sequence[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = []
    alpha = 2.0 / (period + 1.0)
    current: float | None = None
    for value in values:
        current = value if current is None else alpha * value + (1.0 - alpha) * current
        out.append(current)
    return out


def _ema_optional_series(values: Sequence[float | None], period: int) -> list[float | None]:
    """EMA over Pine-style nullable source values.

    ZERO_LAG uses ``close + (close - close[lag])``. In Pine, ``close[lag]`` is
    ``na`` before that history exists, so the derived source is also ``na``.
    ``ta.ema`` begins from the first non-na sample rather than fabricating
    pre-lag source values. Preserve those leading na values explicitly.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = []
    alpha = 2.0 / (period + 1.0)
    current: float | None = None
    for value in values:
        if value is None:
            out.append(current)
            continue
        current = value if current is None else alpha * value + (1.0 - alpha) * current
        out.append(current)
    return out


def _sma_at(values: Sequence[float | None], index: int, period: int) -> float | None:
    if period <= 0 or index + 1 < period:
        return None
    window = values[index - period + 1 : index + 1]
    if any(value is None for value in window):
        return None
    return sum(float(value) for value in window) / period


def _true_ranges(bars: Sequence[MarketBar]) -> list[float]:
    values: list[float] = []
    for index, bar in enumerate(bars):
        high = bar.high_price
        low = bar.low_price
        if index == 0:
            values.append(high - low)
            continue
        previous_close = bars[index - 1].close
        values.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return values


def _rma_series(values: Sequence[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    current = sum(values[:period]) / period
    out[period - 1] = current
    for index in range(period, len(values)):
        current = ((current * (period - 1)) + values[index]) / period
        out[index] = current
    return out


def _atr_series(bars: Sequence[MarketBar], period: int) -> list[float | None]:
    return _rma_series(_true_ranges(bars), period)


def _chop_at(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if index + 1 < period + 1:
        return None
    trs = _true_ranges(bars)
    recent = bars[index - period + 1 : index + 1]
    span = max(bar.high_price for bar in recent) - min(bar.low_price for bar in recent)
    if span <= 0:
        return 100.0
    total_tr = sum(trs[index - period + 1 : index + 1])
    return 100.0 * math.log10(total_tr / span) / math.log10(period)


def _adx_at(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if len(bars) < period + 1 or index < period * 2 - 1:
        return None
    plus_dm = [0.0]
    minus_dm = [0.0]
    for i in range(1, len(bars)):
        up = bars[i].high_price - bars[i - 1].high_price
        down = bars[i - 1].low_price - bars[i].low_price
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    atr = _atr_series(bars, period)
    plus_rma = _rma_series(plus_dm, period)
    minus_rma = _rma_series(minus_dm, period)
    dx: list[float | None] = [None] * len(bars)
    for i in range(len(bars)):
        if atr[i] in (None, 0) or plus_rma[i] is None or minus_rma[i] is None:
            continue
        plus_di = 100.0 * float(plus_rma[i]) / float(atr[i])
        minus_di = 100.0 * float(minus_rma[i]) / float(atr[i])
        denominator = plus_di + minus_di
        dx[i] = 0.0 if denominator == 0 else 100.0 * abs(plus_di - minus_di) / denominator
    valid = [float(value) for value in dx if value is not None]
    if len(valid) < period:
        return None
    adx_values = _rma_series(valid, period)
    offset = next(i for i, value in enumerate(dx) if value is not None)
    lookup = index - offset
    if lookup < 0 or lookup >= len(adx_values):
        return None
    return adx_values[lookup]


def _wma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    weights = range(1, period + 1)
    denominator = period * (period + 1) / 2
    return sum(value * weight for value, weight in zip(values[-period:], weights)) / denominator


def _hma_at(closes: Sequence[float], index: int, period: int) -> float | None:
    if period <= 1:
        return None
    half = max(1, period // 2)
    root = max(1, int(math.sqrt(period)))
    derived: list[float] = []
    for end in range(period, index + 2):
        window = closes[:end]
        full = _wma(window, period)
        short = _wma(window, half)
        if full is not None and short is not None:
            derived.append(2.0 * short - full)
    return _wma(derived, root)


def _cross_over(previous_left: float, current_left: float, previous_right: float, current_right: float) -> bool:
    return previous_left <= previous_right and current_left > current_right


def _cross_under(previous_left: float, current_left: float, previous_right: float, current_right: float) -> bool:
    return previous_left >= previous_right and current_left < current_right


def _zero_lag(params: Mapping[str, Any], bars: Sequence[MarketBar]) -> FrozenSignalDecision:
    length = int(params.get("length", 70))
    multiplier = float(params.get("multiplier", 3.0))
    adx_min = float(params.get("adx_min", 0.0))
    chop_max = float(params.get("chop_max", 0.0))
    atr_pct_min = float(params.get("atr_pct_min", 0.0))
    lag = int(math.floor((length - 1) / 2.0))
    if length <= 1 or multiplier <= 0:
        raise ValueError("ZERO_LAG requires length > 1 and multiplier > 0")
    if len(bars) < max(length * 3, lag + 2, 30):
        return FrozenSignalDecision(False, False, "ZERO_LAG", {"ready": False})

    closes = [bar.close for bar in bars]
    source: list[float | None] = []
    for index, close in enumerate(closes):
        source.append(None if index < lag else close + (close - closes[index - lag]))
    zlema = _ema_optional_series(source, length)
    atr = _atr_series(bars, length)
    upper: list[float | None] = [None] * len(bars)
    lower: list[float | None] = [None] * len(bars)
    for index in range(len(bars)):
        if zlema[index] is None or index + 1 < length * 3:
            continue
        window = atr[index - length * 3 + 1 : index + 1]
        valid = [float(value) for value in window if value is not None]
        if not valid:
            continue
        volatility = max(valid) * multiplier
        upper[index] = float(zlema[index]) + volatility
        lower[index] = float(zlema[index]) - volatility

    trend = 0
    large_green = False
    large_red = False
    for index in range(1, len(bars)):
        if upper[index] is None or upper[index - 1] is None or lower[index] is None or lower[index - 1] is None:
            continue
        prior = trend
        if _cross_over(closes[index - 1], closes[index], float(upper[index - 1]), float(upper[index])):
            trend = 1
        if _cross_under(closes[index - 1], closes[index], float(lower[index - 1]), float(lower[index])):
            trend = -1
        if index == len(bars) - 1:
            large_green = trend == 1 and prior != 1
            large_red = trend == -1 and prior != -1

    index = len(bars) - 1
    adx = _adx_at(bars, index, 14) if adx_min > 0 else None
    chop = _chop_at(bars, index, 14) if chop_max > 0 else None
    atr14 = _atr_series(bars, 14)[index] if atr_pct_min > 0 else None
    atr_pct = None if atr14 is None else float(atr14) / closes[index] * 100.0
    filter_ok = (adx_min <= 0 or (adx is not None and adx > adx_min)) and (
        chop_max <= 0 or (chop is not None and chop < chop_max)
    ) and (atr_pct_min <= 0 or (atr_pct is not None and atr_pct > atr_pct_min))
    return FrozenSignalDecision(
        entry_signal=large_green and filter_ok,
        exit_signal=large_red,
        engine_id="ZERO_LAG",
        diagnostics={
            "ready": True,
            "trend": trend,
            "large_green": large_green,
            "large_red": large_red,
            "adx": adx,
            "chop": chop,
            "atr_pct": atr_pct,
            "filter_ok": filter_ok,
            "zlema": zlema[index],
            "upper_band": upper[index],
            "lower_band": lower[index],
        },
    )


def _bigbeluga(params: Mapping[str, Any], bars: Sequence[MarketBar]) -> FrozenSignalDecision:
    hma_entry = int(params.get("hma_entry", 0))
    hma_exit = int(params.get("hma_exit", 0))
    chop_max = float(params.get("chop_max", 0.0))
    atr_pct_min = float(params.get("atr_pct_min", 0.0))
    if len(bars) <= 301:
        return FrozenSignalDecision(False, False, "BIGBELUGA_RANGE", {"ready": False})

    atr200 = _atr_series(bars, 200)
    width_series: list[float | None] = [None] * len(bars)
    for index in range(len(bars)):
        average = _sma_at(atr200, index, 100)
        width_series[index] = None if average is None else average * 4.0

    value: float | None = None
    upper: float | None = None
    lower: float | None = None
    count = 0
    green_arrow = False
    red_arrow = False
    previous_low = bars[0].low_price
    previous_high = bars[0].high_price
    previous_center: float | None = None

    for index, bar in enumerate(bars):
        if index == 301:
            width = width_series[index]
            if width is not None:
                value = (bar.high_price + bar.low_price) / 2.0
                upper = value + width
                lower = value - width
                count = 0
        center_before_update = value
        upper_before_update = upper
        lower_before_update = lower
        cross_upper = False
        cross_lower = False
        if upper is not None and lower is not None and index > 0:
            cross_upper = previous_low <= upper and bar.low_price > upper
            cross_lower = previous_high >= lower and bar.high_price < lower
            if bar.low_price > upper or bar.high_price < lower:
                count += 1
        if value is not None and (cross_upper or cross_lower or count == 100):
            width = width_series[index]
            if width is not None:
                value = (bar.high_price + bar.low_price) / 2.0
                upper = value + width
                lower = value - width
                count = 0
        unchanged = previous_center is not None and value == previous_center
        if value is not None and upper is not None and lower is not None and index >= 10 and index > 0:
            upper_mid = (value + upper) / 2.0
            lower_mid = (value + lower) / 2.0
            green = unchanged and previous_low <= lower_mid and bar.low_price > lower_mid and bars[index - 10].low_price > lower_mid
            red = unchanged and previous_high >= upper_mid and bar.high_price < upper_mid and bars[index - 10].high_price < upper_mid
            if index == len(bars) - 1:
                green_arrow = green
                red_arrow = red
        previous_center = value
        previous_low = bar.low_price
        previous_high = bar.high_price
        _ = center_before_update, upper_before_update, lower_before_update

    index = len(bars) - 1
    closes = [bar.close for bar in bars]
    chop = _chop_at(bars, index, 14) if chop_max > 0 else None
    atr14 = _atr_series(bars, 14)[index] if atr_pct_min > 0 else None
    atr_pct = None if atr14 is None else float(atr14) / closes[index] * 100.0
    entry_hma = _hma_at(closes, index, hma_entry) if hma_entry > 0 else None
    exit_hma = _hma_at(closes, index, hma_exit) if hma_exit > 0 else None
    filter_ok = (hma_entry <= 0 or (entry_hma is not None and closes[index] > entry_hma)) and (
        chop_max <= 0 or (chop is not None and chop < chop_max)
    ) and (atr_pct_min <= 0 or (atr_pct is not None and atr_pct > atr_pct_min))
    exit_signal = (exit_hma is not None and closes[index] < exit_hma) if hma_exit > 0 else red_arrow
    return FrozenSignalDecision(
        entry_signal=green_arrow and filter_ok,
        exit_signal=exit_signal,
        engine_id="BIGBELUGA_RANGE",
        diagnostics={"ready": True, "green_arrow": green_arrow, "red_arrow": red_arrow, "chop": chop, "atr_pct": atr_pct, "entry_hma": entry_hma, "exit_hma": exit_hma, "filter_ok": filter_ok},
    )


def evaluate_frozen_signal(engine_id: str, parameters: Mapping[str, Any], bars: Sequence[MarketBar]) -> FrozenSignalDecision:
    """Evaluate the current completed chart bar using a frozen engine."""
    engine = engine_id.strip().upper()
    if engine not in SUPPORTED_ENGINES:
        raise ValueError(f"unsupported frozen engine: {engine_id}")
    if not bars:
        return FrozenSignalDecision(False, False, engine, {"ready": False})
    if engine == "ZERO_LAG":
        return _zero_lag(parameters, bars)
    if engine == "VOL_VIDYA":
        entry, exit_signal, diagnostics = evaluate_vol_vidya(parameters, bars)
        return FrozenSignalDecision(entry, exit_signal, engine, diagnostics)
    if engine == "KELTNER_LONG":
        entry, exit_signal, diagnostics = evaluate_keltner_long(parameters, bars)
        return FrozenSignalDecision(entry, exit_signal, engine, diagnostics)
    if engine == "STRATEGY_F":
        entry, exit_signal, diagnostics = evaluate_strategy_f(parameters, bars)
        return FrozenSignalDecision(entry, exit_signal, engine, diagnostics)
    if engine in {"C1_RECON", "C2_RECON"}:
        entry, exit_signal, diagnostics = evaluate_reconstructed_signal(engine, parameters, bars)
        return FrozenSignalDecision(entry, exit_signal, engine, diagnostics)
    return _bigbeluga(parameters, bars)

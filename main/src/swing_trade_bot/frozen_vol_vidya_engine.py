"""Recovered BigBeluga Volumatic VIDYA state machine for frozen stock research.

The implementation follows Section 4.7 of the 2026-09-02 AI Suggestions handoff:
VIDYA -> ATR bands -> trend transition -> delayed visible Green -> recovered
liquidity-dot approximation -> locked confirmed 3/3 swing high -> breakout entry,
with the recovered early-failure technical exit. It is signal logic only and has
no execution, brokerage, order, or capital authority.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .position_state import MarketBar


def _true_ranges(bars: Sequence[MarketBar]) -> list[float]:
    values: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            values.append(bar.high_price - bar.low_price)
        else:
            prior = bars[index - 1].close
            values.append(max(
                bar.high_price - bar.low_price,
                abs(bar.high_price - prior),
                abs(bar.low_price - prior),
            ))
    return values


def _rma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    current = sum(values[:period]) / period
    out[period - 1] = current
    for index in range(period, len(values)):
        current = ((period - 1) * current + values[index]) / period
        out[index] = current
    return out


def _atr(bars: Sequence[MarketBar], period: int) -> list[float | None]:
    return _rma(_true_ranges(bars), period)


def _sma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        return out
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index + 1 >= period:
            out[index] = running / period
    return out


def _vidya(closes: Sequence[float], length: int, momentum_length: int) -> list[float | None]:
    if length <= 0 or momentum_length <= 0:
        raise ValueError("VOL_VIDYA lengths must be positive")
    alpha = 2.0 / (length + 1.0)
    adaptive: list[float] = []
    momentum: list[float] = [0.0]
    for index in range(1, len(closes)):
        momentum.append(closes[index] - closes[index - 1])

    current: float | None = None
    for index, close in enumerate(closes):
        start = max(0, index - momentum_length + 1)
        window = momentum[start : index + 1]
        positive = sum(value if value >= 0 else 0.0 for value in window)
        negative = sum(0.0 if value >= 0 else -value for value in window)
        denominator = positive + negative
        abs_cmo = 0.0 if denominator == 0 else abs(100.0 * (positive - negative) / denominator)
        weight = alpha * abs_cmo / 100.0
        previous = close if current is None else current
        current = weight * close + (1.0 - weight) * previous
        adaptive.append(current)
    return _sma(adaptive, 15)


def _cross_over(prev_left: float, left: float, prev_right: float, right: float) -> bool:
    return prev_left <= prev_right and left > right


def _cross_under(prev_left: float, left: float, prev_right: float, right: float) -> bool:
    return prev_left >= prev_right and left < right


def _pivot_high(values: Sequence[float], index: int, left: int = 3, right: int = 3) -> float | None:
    center = index - right
    if center < left or center + right >= len(values):
        return None
    value = values[center]
    if all(value > values[i] for i in range(center - left, center)) and all(
        value >= values[i] for i in range(center + 1, center + right + 1)
    ):
        return value
    return None


def _pivot_low(values: Sequence[float], index: int, left: int = 3, right: int = 3) -> float | None:
    center = index - right
    if center < left or center + right >= len(values):
        return None
    value = values[center]
    if all(value < values[i] for i in range(center - left, center)) and all(
        value <= values[i] for i in range(center + 1, center + right + 1)
    ):
        return value
    return None


def _chop(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if index + 1 < period + 1:
        return None
    recent = bars[index - period + 1 : index + 1]
    span = max(bar.high_price for bar in recent) - min(bar.low_price for bar in recent)
    if span <= 0:
        return 100.0
    tr = _true_ranges(bars)
    total = sum(tr[index - period + 1 : index + 1])
    return 100.0 * math.log10(total / span) / math.log10(period)


def _adx(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if index < period * 2 - 1:
        return None
    plus_dm = [0.0]
    minus_dm = [0.0]
    for i in range(1, len(bars)):
        up = bars[i].high_price - bars[i - 1].high_price
        down = bars[i - 1].low_price - bars[i].low_price
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    atr = _atr(bars, period)
    plus = _rma(plus_dm, period)
    minus = _rma(minus_dm, period)
    dx: list[float] = []
    offset: int | None = None
    for i in range(len(bars)):
        if atr[i] in (None, 0) or plus[i] is None or minus[i] is None:
            continue
        if offset is None:
            offset = i
        plus_di = 100.0 * float(plus[i]) / float(atr[i])
        minus_di = 100.0 * float(minus[i]) / float(atr[i])
        denominator = plus_di + minus_di
        dx.append(0.0 if denominator == 0 else 100.0 * abs(plus_di - minus_di) / denominator)
    if offset is None or len(dx) < period:
        return None
    adx_values = _rma(dx, period)
    lookup = index - offset
    if lookup < 0 or lookup >= len(adx_values):
        return None
    return adx_values[lookup]


def evaluate_vol_vidya(
    params: Mapping[str, Any],
    bars: Sequence[MarketBar],
) -> tuple[bool, bool, Mapping[str, float | int | bool | None]]:
    """Return current-bar entry/exit signals and recovered-engine diagnostics."""
    vidya_len = int(params.get("vidya_length", params.get("length", 8)))
    momentum_len = int(params.get("momentum_length", params.get("momentum", 15)))
    atr_len = int(params.get("atr_length", 200))
    band_distance = float(params.get("band_distance", params.get("atr_multiplier", 1.5)))
    adx_min = float(params.get("adx_min", 0.0))
    chop_max = float(params.get("chop_max", 0.0))
    atr_pct_min = float(params.get("atr_pct_min", 0.0))
    if vidya_len <= 0 or momentum_len <= 0 or atr_len <= 0 or band_distance <= 0:
        raise ValueError("invalid VOL_VIDYA frozen parameters")
    if len(bars) < max(atr_len, 30):
        return False, False, {"ready": False}

    closes = [bar.close for bar in bars]
    highs = [bar.high_price for bar in bars]
    lows = [bar.low_price for bar in bars]
    vidya = _vidya(closes, vidya_len, momentum_len)
    atr = _atr(bars, atr_len)
    upper: list[float | None] = [None] * len(bars)
    lower: list[float | None] = [None] * len(bars)
    for i in range(len(bars)):
        if vidya[i] is not None and atr[i] is not None:
            upper[i] = float(vidya[i]) + float(atr[i]) * band_distance
            lower[i] = float(vidya[i]) - float(atr[i]) * band_distance

    is_trend_up = False
    prior_trend_up = False
    prior_trend_cross_up = False
    latest_swing_high: float | None = None
    liquidity_level: float | None = None
    liquidity_born: int | None = None
    stage = 0
    locked_swing_high: float | None = None
    prior_smoothed: float | None = None
    smoothed_values: list[float | None] = [None] * len(bars)
    breakout_now = False
    trend_cross_down_now = False
    visible_green_now = False
    green_dot_now = False
    filter_ok_now = False
    adx_now: float | None = None
    chop_now: float | None = None
    atr_pct_now: float | None = None

    for i, bar in enumerate(bars):
        prior_trend_up = is_trend_up
        if i > 0 and upper[i] is not None and upper[i - 1] is not None:
            if _cross_over(closes[i - 1], closes[i], float(upper[i - 1]), float(upper[i])):
                is_trend_up = True
        if i > 0 and lower[i] is not None and lower[i - 1] is not None:
            if _cross_under(closes[i - 1], closes[i], float(lower[i - 1]), float(lower[i])):
                is_trend_up = False

        trend_cross_up = is_trend_up and not prior_trend_up
        trend_cross_down = (not is_trend_up) and prior_trend_up
        visible_green = prior_trend_cross_up
        smoothed = lower[i] if is_trend_up else upper[i]
        if trend_cross_up or trend_cross_down:
            smoothed = None
        smoothed_values[i] = smoothed

        ph = _pivot_high(highs, i, 3, 3)
        if ph is not None:
            latest_swing_high = ph

        pl = _pivot_low(closes, i, 3, 3)
        center = i - 3
        if (
            pl is not None
            and center >= 0
            and smoothed_values[center] is not None
            and lows[center] > float(smoothed_values[center])
        ):
            liquidity_level = lows[center]
            liquidity_born = i

        green_dot = False
        if (
            liquidity_level is not None
            and liquidity_born is not None
            and smoothed is not None
            and prior_smoothed is not None
            and i - liquidity_born < 50
        ):
            green_dot = _cross_over(prior_smoothed, smoothed, liquidity_level, liquidity_level)
        if green_dot or (
            liquidity_born is not None and i - liquidity_born >= 50
        ):
            liquidity_level = None
            liquidity_born = None

        if trend_cross_down:
            stage = 0
            locked_swing_high = None
        if visible_green and is_trend_up:
            stage = 1
        if stage == 1 and green_dot and is_trend_up and latest_swing_high is not None:
            locked_swing_high = latest_swing_high
            stage = 2

        breakout = (
            stage == 2
            and is_trend_up
            and locked_swing_high is not None
            and bar.high_price > locked_swing_high
            and i > 0
            and bars[i - 1].high_price <= locked_swing_high
        )

        if i == len(bars) - 1:
            adx_now = _adx(bars, i, 14) if adx_min > 0 else None
            chop_now = _chop(bars, i, 14) if chop_max > 0 else None
            atr14 = _atr(bars, 14)[i] if atr_pct_min > 0 else None
            atr_pct_now = None if atr14 is None else float(atr14) / closes[i] * 100.0
            filter_ok_now = (
                (adx_min <= 0 or (adx_now is not None and adx_now > adx_min))
                and (chop_max <= 0 or (chop_now is not None and chop_now < chop_max))
                and (atr_pct_min <= 0 or (atr_pct_now is not None and atr_pct_now > atr_pct_min))
            )
            breakout_now = breakout
            trend_cross_down_now = trend_cross_down
            visible_green_now = visible_green
            green_dot_now = green_dot

        if breakout:
            # Pine resets stage after an accepted entry. For signal-only replay the
            # filter is evaluated on this same bar, so reset only when it qualifies.
            adx_value = _adx(bars, i, 14) if adx_min > 0 else None
            chop_value = _chop(bars, i, 14) if chop_max > 0 else None
            atr14_value = _atr(bars, 14)[i] if atr_pct_min > 0 else None
            atr_pct_value = None if atr14_value is None else float(atr14_value) / closes[i] * 100.0
            qualifies = (
                (adx_min <= 0 or (adx_value is not None and adx_value > adx_min))
                and (chop_max <= 0 or (chop_value is not None and chop_value < chop_max))
                and (atr_pct_min <= 0 or (atr_pct_value is not None and atr_pct_value > atr_pct_min))
            )
            if qualifies:
                stage = 0

        prior_trend_cross_up = trend_cross_up
        prior_smoothed = smoothed

    index = len(bars) - 1
    smoothed_now = smoothed_values[index]
    early_failure = trend_cross_down_now or (
        is_trend_up and smoothed_now is not None and closes[index] < smoothed_now
    )
    entry = breakout_now and filter_ok_now
    diagnostics = {
        "ready": True,
        "vidya": vidya[index],
        "upper_band": upper[index],
        "lower_band": lower[index],
        "is_trend_up": is_trend_up,
        "visible_green_arrow": visible_green_now,
        "green_dot": green_dot_now,
        "stage": stage,
        "locked_swing_high": locked_swing_high,
        "breakout": breakout_now,
        "early_failure": early_failure,
        "adx": adx_now,
        "chop": chop_now,
        "atr_pct": atr_pct_now,
        "filter_ok": filter_ok_now,
    }
    return entry, early_failure, diagnostics

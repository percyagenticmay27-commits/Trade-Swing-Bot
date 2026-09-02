"""Recovered Strategy F (ITC/TEMA) signal engine for frozen stock research.

The mathematics and state transition contract come from the authoritative
2026-09-02 AI Suggestions handoff.  This module is research/signal logic only;
it exposes no brokerage, order, or capital authority.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .position_state import MarketBar


def _ema(values: Sequence[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    alpha = 2.0 / (period + 1.0)
    out: list[float] = []
    current: float | None = None
    for value in values:
        current = value if current is None else alpha * value + (1.0 - alpha) * current
        out.append(current)
    return out


def _sma_at(values: Sequence[float], index: int, period: int) -> float | None:
    if period <= 0 or index + 1 < period:
        return None
    window = values[index - period + 1 : index + 1]
    return sum(window) / period


def _true_ranges(bars: Sequence[MarketBar]) -> list[float]:
    values: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            values.append(bar.high_price - bar.low_price)
            continue
        previous_close = bars[index - 1].close
        values.append(max(
            bar.high_price - bar.low_price,
            abs(bar.high_price - previous_close),
            abs(bar.low_price - previous_close),
        ))
    return values


def _chop_at(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if index + 1 < period:
        return None
    trs = _true_ranges(bars)
    recent = bars[index - period + 1 : index + 1]
    span = max(bar.high_price for bar in recent) - min(bar.low_price for bar in recent)
    if span <= 0:
        return 100.0
    total_tr = sum(trs[index - period + 1 : index + 1])
    return 100.0 * math.log10(total_tr / span) / math.log10(period)


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


def _rsi_at(closes: Sequence[float], index: int, period: int = 14) -> float | None:
    if index < period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, index + 1):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _adx_at(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if index < period * 2 - 1:
        return None
    tr = _true_ranges(bars)
    plus_dm = [0.0]
    minus_dm = [0.0]
    for i in range(1, len(bars)):
        up = bars[i].high_price - bars[i - 1].high_price
        down = bars[i - 1].low_price - bars[i].low_price
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)

    def rma(values: Sequence[float]) -> list[float | None]:
        out: list[float | None] = [None] * len(values)
        if len(values) < period:
            return out
        current = sum(values[:period]) / period
        out[period - 1] = current
        for j in range(period, len(values)):
            current = ((current * (period - 1)) + values[j]) / period
            out[j] = current
        return out

    atr = rma(tr)
    plus = rma(plus_dm)
    minus = rma(minus_dm)
    dx: list[float] = []
    for i in range(len(bars)):
        if atr[i] in (None, 0) or plus[i] is None or minus[i] is None:
            continue
        p = 100.0 * float(plus[i]) / float(atr[i])
        m = 100.0 * float(minus[i]) / float(atr[i])
        denom = p + m
        dx.append(0.0 if denom == 0 else 100.0 * abs(p - m) / denom)
    if len(dx) < period:
        return None
    current = sum(dx[:period]) / period
    for value in dx[period:]:
        current = ((current * (period - 1)) + value) / period
    return current


def evaluate_strategy_f(
    parameters: Mapping[str, Any],
    bars: Sequence[MarketBar],
) -> tuple[bool, bool, Mapping[str, float | int | bool | None]]:
    """Evaluate the current confirmed bar using the recovered Strategy F rules."""
    hma_length = int(parameters.get("hma_length", 0))
    chop_max = float(parameters.get("chop_max", 0.0))
    adx_min = float(parameters.get("adx_min", 0.0))
    rsi_min = float(parameters.get("rsi_min", 0.0))
    if len(bars) < 3:
        return False, False, {"ready": False}

    closes = [bar.close for bar in bars]
    ema1 = _ema(closes, 44)
    ema2 = _ema(ema1, 44)
    ema3 = _ema(ema2, 44)
    tema = [3.0 * (a - b) + c for a, b, c in zip(ema1, ema2, ema3)]
    fast = _ema(closes, 17)
    slow = _ema(closes, 26)
    macd = [a - b for a, b in zip(fast, slow)]

    last_tran = False
    current_buy = False
    current_sell = False
    signal_value: float | None = None
    for index in range(1, len(bars)):
        signal_value = _sma_at(macd, index, 9)
        if signal_value is None:
            continue
        trend_up = tema[index] >= tema[index - 1]
        trend_down = tema[index] < tema[index - 1]
        buy_event = trend_up and not last_tran and macd[index] >= signal_value
        sell_event = trend_down and last_tran and macd[index] < signal_value
        if buy_event:
            last_tran = True
        if sell_event:
            last_tran = False
        if index == len(bars) - 1:
            current_buy = buy_event
            current_sell = sell_event

    index = len(bars) - 1
    hma = _hma_at(closes, index, hma_length) if hma_length > 0 else None
    chop = _chop_at(bars, index, 14) if chop_max > 0 else None
    adx = _adx_at(bars, index, 14) if adx_min > 0 else None
    rsi = _rsi_at(closes, index, 14) if rsi_min > 0 else None
    filter_ok = (
        (hma_length <= 0 or (hma is not None and closes[index] > hma))
        and (chop_max <= 0 or (chop is not None and chop < chop_max))
        and (adx_min <= 0 or (adx is not None and adx > adx_min))
        and (rsi_min <= 0 or (rsi is not None and rsi > rsi_min))
    )
    return (
        current_buy and filter_ok,
        current_sell,
        {
            "ready": signal_value is not None,
            "tema": tema[index],
            "macd": macd[index],
            "signal": signal_value,
            "last_tran": last_tran,
            "buy_event": current_buy,
            "sell_event": current_sell,
            "hma": hma,
            "chop": chop,
            "adx": adx,
            "rsi": rsi,
            "filter_ok": filter_ok,
        },
    )

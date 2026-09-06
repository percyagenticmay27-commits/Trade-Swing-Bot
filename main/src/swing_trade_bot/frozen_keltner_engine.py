"""Recovered KELTNER_LONG signal engine for frozen stock research.

Implements the authoritative OHLC4 / SMA-seeded Wilder-RMA construction from
2026-09-02 handoff. Research/signal logic only; no execution authority.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .position_state import MarketBar


def _rma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return out
    current = sum(values[:period]) / period
    out[period - 1] = current
    for index in range(period, len(values)):
        current = ((current * (period - 1)) + values[index]) / period
        out[index] = current
    return out


def _tr(bars: Sequence[MarketBar]) -> list[float]:
    out: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            out.append(bar.high_price - bar.low_price)
            continue
        prior = bars[index - 1].close
        out.append(max(bar.high_price - bar.low_price, abs(bar.high_price - prior), abs(bar.low_price - prior)))
    return out


def _wma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    denominator = period * (period + 1) / 2
    return sum(v * w for v, w in zip(values[-period:], range(1, period + 1))) / denominator


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


def _chop_at(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if index + 1 < period:
        return None
    trs = _tr(bars)
    recent = bars[index - period + 1:index + 1]
    span = max(x.high_price for x in recent) - min(x.low_price for x in recent)
    if span <= 0:
        return 100.0
    return 100.0 * math.log10(sum(trs[index - period + 1:index + 1]) / span) / math.log10(period)


def _adx_at(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if index < period * 2 - 1:
        return None
    plus_dm = [0.0]
    minus_dm = [0.0]
    for i in range(1, len(bars)):
        up = bars[i].high_price - bars[i - 1].high_price
        down = bars[i - 1].low_price - bars[i].low_price
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    atr = _rma(_tr(bars), period)
    plus = _rma(plus_dm, period)
    minus = _rma(minus_dm, period)
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
    adx = _rma(dx, period)
    return next((float(v) for v in reversed(adx) if v is not None), None)


def evaluate_keltner_long(
    parameters: Mapping[str, Any],
    bars: Sequence[MarketBar],
) -> tuple[bool, bool, Mapping[str, float | int | bool | None]]:
    kc_len = int(parameters.get("kc_length", 14))
    factor = float(parameters.get("kc_factor", 1.0))
    hma_length = int(parameters.get("hma_length", 0))
    chop_max = float(parameters.get("chop_max", 0.0))
    adx_min = float(parameters.get("adx_min", 0.0))
    atr_pct_min = float(parameters.get("atr_pct_min", 0.0))
    exit_mode = str(parameters.get("exit_mode", "BASIS")).strip().upper()
    valid_exit_modes = {"UPPER", "BASIS", "LOWER", "LOWER_AFTER_UPPER_ARM"}
    if exit_mode not in valid_exit_modes:
        raise ValueError(
            "KELTNER_LONG exit_mode must be UPPER, BASIS, LOWER, or LOWER_AFTER_UPPER_ARM"
        )
    if kc_len <= 0 or factor <= 0:
        raise ValueError("KELTNER_LONG requires positive kc_length and kc_factor")
    if len(bars) < max(kc_len + 2, hma_length + 2 if hma_length > 0 else 0, 30):
        return False, False, {"ready": False}

    src = [(b.open_price + b.high_price + b.low_price + b.close) / 4.0 for b in bars]
    basis = _rma(src, kc_len)
    rng = _rma(_tr(bars), kc_len)
    upper: list[float | None] = []
    lower: list[float | None] = []
    for b, r in zip(basis, rng):
        upper.append(None if b is None or r is None else float(b) + factor * float(r))
        lower.append(None if b is None or r is None else float(b) - factor * float(r))

    closes = [b.close for b in bars]
    position_open = False
    armed = False
    current_entry = False
    current_exit = False
    current_hma: float | None = None
    current_chop: float | None = None
    current_adx: float | None = None
    current_atr_pct: float | None = None
    current_filter_ok = False

    for index in range(1, len(bars)):
        if basis[index] is None or upper[index] is None or lower[index] is None or lower[index - 1] is None:
            continue
        hma = _hma_at(closes, index, hma_length) if hma_length > 0 else None
        chop = _chop_at(bars, index, 14) if chop_max > 0 else None
        adx = _adx_at(bars, index, 14) if adx_min > 0 else None
        atr14 = _rma(_tr(bars), 14)[index] if atr_pct_min > 0 else None
        atr_pct = None if atr14 is None else float(atr14) / closes[index] * 100.0
        filter_ok = (
            (hma_length <= 0 or (hma is not None and closes[index] > hma))
            and (chop_max <= 0 or (chop is not None and chop < chop_max))
            and (adx_min <= 0 or (adx is not None and adx > adx_min))
            and (atr_pct_min <= 0 or (atr_pct is not None and atr_pct > atr_pct_min))
        )
        cross_lower = closes[index - 1] <= float(lower[index - 1]) and closes[index] > float(lower[index])
        entry = (not position_open) and cross_lower and filter_ok
        if entry:
            position_open = True
            armed = False
        if position_open and bars[index].high_price >= float(upper[index]):
            armed = True
        if exit_mode == "LOWER":
            tech_exit = position_open and closes[index] < float(lower[index])
        elif exit_mode == "LOWER_AFTER_UPPER_ARM":
            tech_exit = position_open and armed and closes[index] < float(lower[index])
        else:
            exit_level = float(upper[index]) if exit_mode == "UPPER" else float(basis[index])
            tech_exit = position_open and armed and closes[index] < exit_level
        if tech_exit:
            position_open = False
            armed = False
        if index == len(bars) - 1:
            current_entry = entry
            current_exit = tech_exit
            current_hma = hma
            current_chop = chop
            current_adx = adx
            current_atr_pct = atr_pct
            current_filter_ok = filter_ok

    index = len(bars) - 1
    return (
        current_entry,
        current_exit,
        {
            "ready": basis[index] is not None,
            "basis": basis[index],
            "upper": upper[index],
            "lower": lower[index],
            "hma": current_hma,
            "chop": current_chop,
            "adx": current_adx,
            "atr_pct": current_atr_pct,
            "filter_ok": current_filter_ok,
            "armed": armed,
        },
    )

"""Paper-only C1/C2 reconstructed stock signal engines.

These implementations are project-authorized AI reconstructions from the
2026-09-02 strategy handoff. They are not recovered original Pine source.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .position_state import MarketBar

RECONSTRUCTED_ENGINES = {"C1_RECON", "C2_RECON"}


def _sma_at(values: Sequence[float | None], index: int, period: int) -> float | None:
    if period <= 0 or index + 1 < period:
        return None
    window = values[index - period + 1:index + 1]
    if any(value is None for value in window):
        return None
    return sum(float(value) for value in window) / period


def _stoch_raw(bars: Sequence[MarketBar], period: int = 7) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    for index in range(period - 1, len(bars)):
        window = bars[index - period + 1:index + 1]
        low = min(bar.low_price for bar in window)
        high = max(bar.high_price for bar in window)
        span = high - low
        out[index] = 0.0 if span <= 0 else 100.0 * (bars[index].close - low) / span
    return out


def _sma_series(values: Sequence[float | None], period: int) -> list[float | None]:
    return [_sma_at(values, index, period) for index in range(len(values))]


def _true_ranges(bars: Sequence[MarketBar]) -> list[float]:
    out: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            out.append(bar.high_price - bar.low_price)
        else:
            prior = bars[index - 1].close
            out.append(max(bar.high_price - bar.low_price, abs(bar.high_price - prior), abs(bar.low_price - prior)))
    return out


def _rma_series(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    current = sum(values[:period]) / period
    out[period - 1] = current
    for index in range(period, len(values)):
        current = ((current * (period - 1)) + values[index]) / period
        out[index] = current
    return out


def _chop_at(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if index + 1 < period + 1:
        return None
    trs = _true_ranges(bars)
    recent = bars[index - period + 1:index + 1]
    span = max(bar.high_price for bar in recent) - min(bar.low_price for bar in recent)
    if span <= 0:
        return 100.0
    return 100.0 * math.log10(sum(trs[index - period + 1:index + 1]) / span) / math.log10(period)


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
    atr = _rma_series(_true_ranges(bars), period)
    plus_rma = _rma_series(plus_dm, period)
    minus_rma = _rma_series(minus_dm, period)
    dx: list[float | None] = [None] * len(bars)
    for i in range(len(bars)):
        if atr[i] in (None, 0) or plus_rma[i] is None or minus_rma[i] is None:
            continue
        plus_di = 100.0 * float(plus_rma[i]) / float(atr[i])
        minus_di = 100.0 * float(minus_rma[i]) / float(atr[i])
        denom = plus_di + minus_di
        dx[i] = 0.0 if denom == 0 else 100.0 * abs(plus_di - minus_di) / denom
    first = next((i for i, value in enumerate(dx) if value is not None), None)
    if first is None:
        return None
    valid = [float(value) for value in dx[first:] if value is not None]
    adx = _rma_series(valid, period)
    lookup = index - first
    return None if lookup < 0 or lookup >= len(adx) else adx[lookup]


def _rsi_at(bars: Sequence[MarketBar], index: int, period: int = 14) -> float | None:
    if index < period:
        return None
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(bars)):
        change = bars[i].close - bars[i - 1].close
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = _rma_series(gains, period)[index]
    avg_loss = _rma_series(losses, period)[index]
    if avg_gain is None or avg_loss is None:
        return None
    if avg_loss == 0:
        return 100.0
    rs = float(avg_gain) / float(avg_loss)
    return 100.0 - 100.0 / (1.0 + rs)


def _wma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    denom = period * (period + 1) / 2
    return sum(value * weight for value, weight in zip(values[-period:], range(1, period + 1))) / denom


def _hma_at(closes: Sequence[float], index: int, period: int) -> float | None:
    if period <= 1:
        return None
    half = max(1, period // 2)
    root = max(1, int(math.sqrt(period)))
    derived: list[float] = []
    for end in range(period, index + 2):
        full = _wma(closes[:end], period)
        short = _wma(closes[:end], half)
        if full is not None and short is not None:
            derived.append(2.0 * short - full)
    return _wma(derived, root)


def _cross_over(pl: float, cl: float, pr: float, cr: float) -> bool:
    return pl <= pr and cl > cr


def _cross_under(pl: float, cl: float, pr: float, cr: float) -> bool:
    return pl >= pr and cl < cr


def _filters(params: Mapping[str, Any], bars: Sequence[MarketBar]) -> tuple[bool, dict[str, float | None]]:
    index = len(bars) - 1
    closes = [bar.close for bar in bars]
    hma_len = int(params.get("hma_length", 0))
    chop_max = float(params.get("chop_max", 0.0))
    adx_min = float(params.get("adx_min", 0.0))
    rsi_min = float(params.get("rsi_min", 0.0))
    hma = _hma_at(closes, index, hma_len) if hma_len > 0 else None
    chop = _chop_at(bars, index) if chop_max > 0 else None
    adx = _adx_at(bars, index) if adx_min > 0 else None
    rsi = _rsi_at(bars, index) if rsi_min > 0 else None
    ok = (hma_len <= 0 or (hma is not None and closes[index] > hma)) and (chop_max <= 0 or (chop is not None and chop < chop_max)) and (adx_min <= 0 or (adx is not None and adx > adx_min)) and (rsi_min <= 0 or (rsi is not None and rsi > rsi_min))
    return ok, {"hma": hma, "chop": chop, "adx": adx, "rsi": rsi}


def evaluate_reconstructed_signal(engine_id: str, parameters: Mapping[str, Any], bars: Sequence[MarketBar]) -> tuple[bool, bool, dict[str, Any]]:
    engine = engine_id.strip().upper()
    if engine not in RECONSTRUCTED_ENGINES:
        raise ValueError(f"unsupported reconstructed engine: {engine_id}")
    if len(bars) < 16:
        return False, False, {"ready": False, "ai_reconstructed": True}
    raw = _stoch_raw(bars, 7)
    if engine == "C1_RECON":
        red_k = _sma_series(raw, 5)
        blue_k = _sma_series(raw, 6)
        blue_d = _sma_series(blue_k, 3)
        i = len(bars) - 1
        values = (blue_d[i - 1], blue_d[i], red_k[i - 1], red_k[i])
        if any(value is None for value in values):
            return False, False, {"ready": False, "ai_reconstructed": True}
        entry_core = _cross_over(float(values[0]), float(values[1]), float(values[2]), float(values[3]))
        exit_core = _cross_over(float(values[2]), float(values[3]), float(values[0]), float(values[1]))
        filter_ok, diagnostics = _filters(parameters, bars)
        return entry_core and filter_ok, exit_core, {"ready": True, "ai_reconstructed": True, "filter_ok": filter_ok, **diagnostics}

    red_k = _sma_series(raw, 7)
    red_d = _sma_series(red_k, 2)
    blue_k = _sma_series(raw, 5)
    blue_d = _sma_series(blue_k, 3)
    i = len(bars) - 1
    values = (blue_k[i - 1], blue_k[i], red_k[i - 1], red_k[i], blue_d[i - 1], blue_d[i], red_d[i - 1], red_d[i])
    if any(value is None for value in values):
        return False, False, {"ready": False, "ai_reconstructed": True}
    bk0, bk1, rk0, rk1, bd0, bd1, rd0, rd1 = (float(value) for value in values)
    mode = str(parameters.get("mode", "K_K_CROSS")).strip().upper()
    if mode == "K_K_CROSS":
        entry_core = _cross_over(bk0, bk1, rk0, rk1)
        exit_core = _cross_under(bk0, bk1, rk0, rk1)
    elif mode == "BOTH_BULLISH":
        bull0, bull1 = bk0 > rk0 and bd0 > rd0, bk1 > rk1 and bd1 > rd1
        bear0, bear1 = bk0 < rk0 and bd0 < rd0, bk1 < rk1 and bd1 < rd1
        entry_core, exit_core = bull1 and not bull0, bear1 and not bear0
    else:
        raise ValueError("C2_RECON mode must be K_K_CROSS or BOTH_BULLISH")
    filter_ok, diagnostics = _filters(parameters, bars)
    return entry_core and filter_ok, exit_core, {"ready": True, "ai_reconstructed": True, "mode": mode, "filter_ok": filter_ok, **diagnostics}

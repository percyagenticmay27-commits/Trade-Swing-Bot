"""Dependency-free technical indicator functions."""

from __future__ import annotations

from collections.abc import Sequence
from math import fsum


def sma(values: Sequence[float], period: int) -> float | None:
    """Return the simple moving average of the latest period."""
    _validate_period(period)
    if len(values) < period:
        return None
    return fsum(values[-period:]) / period


def ema(values: Sequence[float], period: int) -> float | None:
    """Return an EMA seeded with an SMA, using all supplied observations."""
    _validate_period(period)
    if len(values) < period:
        return None
    result = fsum(values[:period]) / period
    multiplier = 2.0 / (period + 1)
    for value in values[period:]:
        result = (value - result) * multiplier + result
    return result


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    """Return Wilder's RSI for the latest close."""
    _validate_period(period)
    if len(values) < period + 1:
        return None

    changes = [current - previous for previous, current in zip(values, values[1:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_gain = fsum(gains[:period]) / period
    average_loss = fsum(losses[:period]) / period

    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period

    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def volume_average(volumes: Sequence[float], period: int = 20) -> float | None:
    """Return the simple average volume for the supplied lookback."""
    return sma(volumes, period)


def _validate_period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be positive")

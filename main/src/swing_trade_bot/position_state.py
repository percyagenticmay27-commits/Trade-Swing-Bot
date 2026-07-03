"""Market data, paper position state, and strategy output models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

SignalStatus = Literal["BUY", "HOLD", "SELL", "WAIT_FOR_REENTRY"]


@dataclass(frozen=True, slots=True)
class MarketBar:
    """A completed daily bar with close-only backward compatibility."""

    date: date
    close: float
    volume: float
    open: float | None = None
    high: float | None = None
    low: float | None = None

    def __post_init__(self) -> None:
        if self.close <= 0:
            raise ValueError("close must be positive")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")
        if any(price is not None and price <= 0 for price in (self.open, self.high, self.low)):
            raise ValueError("OHLC prices must be positive")
        if self.high is not None and self.high < max(self.open_price, self.close):
            raise ValueError("high cannot be below open or close")
        if self.low is not None and self.low > min(self.open_price, self.close):
            raise ValueError("low cannot be above open or close")
        if self.high is not None and self.low is not None and self.high < self.low:
            raise ValueError("high cannot be below low")

    @property
    def open_price(self) -> float:
        return self.close if self.open is None else self.open

    @property
    def high_price(self) -> float:
        return max(self.open_price, self.close) if self.high is None else self.high

    @property
    def low_price(self) -> float:
        return min(self.open_price, self.close) if self.low is None else self.low


@dataclass(slots=True)
class PositionState:
    """Persistent in-memory paper position and re-entry state."""

    symbol: str
    is_open: bool = False
    entry_price: float | None = None
    highest_close: float | None = None
    current_stop: float | None = None
    awaiting_reentry: bool = False
    last_exit_price: float | None = None
    position_size: float | None = None


@dataclass(frozen=True, slots=True)
class SignalResult:
    """Complete user-facing strategy result for one ticker."""

    symbol: str
    signal: SignalStatus
    reason: str
    entry_price: float | None
    current_price: float
    highest_price_since_entry: float | None
    stop_price: float | None
    unrealized_gain_loss_percent: float | None
    suggested_position_size: float | None

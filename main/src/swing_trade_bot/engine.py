"""Stateful paper-trading swing strategy engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any, cast

from .broker_adapter import BrokerAdapter
from .config import StrategyConfig
from .indicators import ema, rsi, sma, volume_average
from .position_state import MarketBar, PositionState, SignalResult, SignalStatus


class SwingTradeEngine:
    """Evaluate completed daily bars and maintain simulated positions."""

    def __init__(
        self,
        config: StrategyConfig | None = None,
        *,
        account_value: float = 100_000.0,
        paper_trade_mode: bool = True,
        broker_adapter: BrokerAdapter | None = None,
    ) -> None:
        if not paper_trade_mode:
            raise ValueError("Live trading is not implemented; paper_trade_mode must be True")
        self.config = config or StrategyConfig()
        if account_value <= 0:
            raise ValueError("account_value must be positive")
        self.account_value = account_value
        self.paper_trade_mode = paper_trade_mode
        self.broker_adapter = broker_adapter
        self.positions = {
            symbol: PositionState(symbol=symbol) for symbol in self.config.symbols
        }

    def evaluate(
        self,
        symbol: str,
        bars: Sequence[MarketBar],
        benchmark_data: Mapping[str, Sequence[MarketBar]] | None = None,
        earnings_dates: Mapping[str, date] | None = None,
    ) -> SignalResult:
        """Evaluate one ticker and update its simulated position state."""
        normalized_symbol = symbol.upper()
        if normalized_symbol not in self.positions:
            raise ValueError(f"Unsupported symbol: {normalized_symbol}")
        required = max(
            self.config.ema_period,
            self.config.sma_period,
            self.config.rsi_period + 1,
            self.config.volume_period + 1,
        )
        if len(bars) < required:
            raise ValueError(f"At least {required} completed daily bars are required")
        if any(left.date >= right.date for left, right in zip(bars, bars[1:])):
            raise ValueError("bars must be strictly chronological")

        closes = [bar.close for bar in bars]
        current = bars[-1]
        current_ema = _required(ema(closes, self.config.ema_period), "EMA")
        current_sma = _required(sma(closes, self.config.sma_period), "SMA")
        current_rsi = _required(rsi(closes, self.config.rsi_period), "RSI")
        # Exclude today's volume so the comparison is not diluted by itself.
        average_volume = _required(
            volume_average([bar.volume for bar in bars[:-1]], self.config.volume_period),
            "volume average",
        )
        state = self.positions[normalized_symbol]
        earnings_status = self._earnings_status(normalized_symbol, current.date, earnings_dates)

        if state.is_open and earnings_status.force_exit:
            result = self._result(
                state,
                "SELL",
                current.close,
                (
                    f"{earnings_status.reason}; close {normalized_symbol} and move proceeds "
                    f"to {self.config.earnings_safe_haven_symbol}"
                ),
            )
            self._close_position(state, current.close)
            return result

        if state.is_open:
            return self._manage_open_position(state, current.close)
        if state.awaiting_reentry:
            near_ema = abs(current.close - current_ema) / current_ema <= self.config.ema_near_tolerance
            checks = {
                "price is near the 20-day EMA": near_ema,
                "RSI is below 55": current_rsi < self.config.reentry_rsi_max,
                "price is above the 50-day SMA": current.close > current_sma,
            }
            checks.update(self._market_filter_checks(normalized_symbol, benchmark_data))
            if earnings_status.block_entry:
                checks[earnings_status.reason] = False
            if all(checks.values()):
                self._open_position(state, current.close)
                return self._result(state, "BUY", current.close, "RE-ENTRY BUY: pullback conditions are met")
            return self._result(state, "WAIT_FOR_REENTRY", current.close, _failed_reason(checks))

        checks = {
            "price is above the 20-day EMA": current.close > current_ema,
            "price is above the 50-day SMA": current.close > current_sma,
            "RSI is between 45 and 65": self.config.entry_rsi_min <= current_rsi <= self.config.entry_rsi_max,
            "volume is above its prior 20-day average": current.volume > average_volume,
        }
        checks.update(self._market_filter_checks(normalized_symbol, benchmark_data))
        if earnings_status.block_entry:
            checks[earnings_status.reason] = False
        if all(checks.values()):
            self._open_position(state, current.close)
            return self._result(state, "BUY", current.close, "All initial entry conditions are met")
        return self._result(state, "HOLD", current.close, _failed_reason(checks, prefix="No entry: "))

    def evaluate_all(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        earnings_dates: Mapping[str, date] | None = None,
    ) -> list[SignalResult]:
        """Evaluate every configured symbol in configuration order."""
        normalized_data = {symbol.upper(): bars for symbol, bars in market_data.items()}
        missing = [symbol for symbol in self.config.symbols if symbol not in normalized_data]
        if missing:
            raise ValueError(f"Missing market data for: {', '.join(missing)}")
        return [
            self.evaluate(symbol, normalized_data[symbol], normalized_data, earnings_dates)
            for symbol in self.config.symbols
        ]

    def calculate_position_size(self) -> float:
        """Return a dollar allocation constrained by risk and the 20% cap."""
        risk_based_size = (
            self.account_value
            * self.config.max_risk_per_trade
            / self.config.initial_stop_percent
        )
        position_cap = self.account_value * self.config.max_position_percent
        return min(risk_based_size, position_cap)

    def _market_filter_checks(
        self,
        symbol: str,
        benchmark_data: Mapping[str, Sequence[MarketBar]] | None,
    ) -> dict[str, bool]:
        normalized = {
            key.upper(): value for key, value in (benchmark_data or {}).items()
        }
        checks = {
            "SPY is above its 50-day SMA": _benchmark_above_sma(
                normalized.get("SPY"), self.config.sma_period
            )
        }
        if symbol in {"SOXL", "TQQQ"}:
            checks["QQQ is above its 50-day SMA"] = _benchmark_above_sma(
                normalized.get("QQQ"), self.config.sma_period
            )
        return checks

    def _manage_open_position(self, state: PositionState, close: float) -> SignalResult:
        assert state.entry_price is not None
        state.highest_close = max(state.highest_close or state.entry_price, close)
        peak_multiple = state.highest_close / state.entry_price

        if peak_multiple >= 1.0 + self.config.wide_trailing_trigger:
            proposed_stop = state.highest_close * (1.0 - self.config.wide_trailing_percent)
            stop_reason = "10% trailing stop is active after reaching +30%"
        elif peak_multiple >= 1.0 + self.config.tight_trailing_trigger:
            proposed_stop = state.highest_close * (1.0 - self.config.tight_trailing_percent)
            stop_reason = "5% trailing stop is active after reaching +20%"
        elif peak_multiple >= 1.0 + self.config.break_even_trigger:
            proposed_stop = state.entry_price
            stop_reason = "stop is at break-even after reaching +15%"
        else:
            proposed_stop = state.entry_price * (1.0 - self.config.initial_stop_percent)
            stop_reason = "initial 10% stop is active"

        # Stops ratchet upward only, including when a wider trailing tier activates.
        state.current_stop = max(state.current_stop or proposed_stop, proposed_stop)

        if close < state.current_stop:
            result = self._result(state, "SELL", close, f"Close is below stop; {stop_reason}")
            self._close_position(state, close)
            return result
        return self._result(state, "HOLD", close, stop_reason)

    def _open_position(self, state: PositionState, price: float) -> None:
        state.is_open = True
        state.awaiting_reentry = False
        state.entry_price = price
        state.highest_close = price
        state.current_stop = price * (1.0 - self.config.initial_stop_percent)
        state.position_size = self.calculate_position_size()

    @staticmethod
    def _close_position(state: PositionState, price: float) -> None:
        state.is_open = False
        state.awaiting_reentry = True
        state.last_exit_price = price
        state.position_size = None

    def _earnings_status(
        self,
        symbol: str,
        current_date: date,
        earnings_dates: Mapping[str, date] | None,
    ) -> "_EarningsStatus":
        source = self._earnings_source_for(symbol)
        if source is None or not earnings_dates:
            return _EarningsStatus()
        normalized_dates = {key.upper(): value for key, value in earnings_dates.items()}
        earnings_date = normalized_dates.get(source)
        if earnings_date is None:
            return _EarningsStatus()

        label = source if source == symbol else f"{symbol} is earnings sensitive through {source}"
        days_until = _business_days_between(current_date, earnings_date)
        if 0 <= days_until <= self.config.earnings_forced_exit_days:
            return _EarningsStatus(
                block_entry=True,
                force_exit=True,
                reason=f"{label} earnings forced-exit window is active",
            )
        if 0 <= days_until <= self.config.earnings_entry_blackout_days:
            return _EarningsStatus(
                block_entry=True,
                reason=f"{label} earnings entry blackout is active",
            )
        days_after = _business_days_between(earnings_date, current_date)
        if 0 <= days_after <= self.config.earnings_post_wait_days:
            return _EarningsStatus(
                block_entry=True,
                reason=f"{label} post-earnings wait period is active",
            )
        return _EarningsStatus()

    def _earnings_source_for(self, symbol: str) -> str | None:
        normalized_symbol = symbol.upper()
        if normalized_symbol in {source.upper() for source, _target in self.config.underlying_exposure_map}:
            return normalized_symbol
        for source, target in self.config.underlying_exposure_map:
            if normalized_symbol == target.upper():
                return source.upper()
        return None

    @staticmethod
    def _result(state: PositionState, status: str, price: float, reason: str) -> SignalResult:
        gain = None if state.entry_price is None else ((price / state.entry_price) - 1.0) * 100.0
        return SignalResult(
            symbol=state.symbol,
            signal=cast(SignalStatus, status),
            reason=reason,
            entry_price=state.entry_price,
            current_price=price,
            highest_price_since_entry=state.highest_close,
            stop_price=state.current_stop,
            unrealized_gain_loss_percent=gain if state.is_open or status == "SELL" else None,
            suggested_position_size=state.position_size,
        )

    # Future Agentic/Robinhood adapter boundary. These methods intentionally do
    # not connect to a broker while the engine is paper-only.
    def get_historical_prices(self, symbol: str) -> Sequence[MarketBar]:
        if self.broker_adapter is None:
            raise NotImplementedError("Attach a read-only market-data adapter in a future release")
        return self.broker_adapter.get_historical_prices(symbol)

    def get_current_positions(self) -> Mapping[str, PositionState]:
        return self.positions.copy()

    def review_order(self, symbol: str, side: str, quantity: float) -> Any:
        if self.broker_adapter is None:
            raise NotImplementedError("Broker order review is not connected")
        return self.broker_adapter.review_order(symbol, side, quantity)

    def place_order(self, symbol: str, side: str, quantity: float) -> Any:
        raise RuntimeError("Real order placement is disabled in paper-trading mode")


def _required(value: float | None, name: str) -> float:
    if value is None:
        raise ValueError(f"Insufficient data for {name}")
    return value


def _failed_reason(checks: Mapping[str, bool], prefix: str = "Waiting: ") -> str:
    failed = [description for description, passed in checks.items() if not passed]
    return prefix + "; ".join(failed)


def _benchmark_above_sma(bars: Sequence[MarketBar] | None, period: int) -> bool:
    if bars is None or len(bars) < period:
        return False
    closes = [bar.close for bar in bars]
    average = sma(closes, period)
    return average is not None and closes[-1] > average


class _EarningsStatus:
    def __init__(self, *, block_entry: bool = False, force_exit: bool = False, reason: str = "") -> None:
        self.block_entry = block_entry
        self.force_exit = force_exit
        self.reason = reason


def _business_days_between(start: date, end: date) -> int:
    """Count weekdays after start through end; negative when end is before start."""
    if start == end:
        return 0
    step = 1 if end > start else -1
    current = start
    days = 0
    while current != end:
        current += timedelta(days=step)
        if current.weekday() < 5:
            days += step
    return days

"""Configuration for the paper swing-trading strategy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    """All indicator, risk, sizing, and re-entry thresholds."""

    symbols: tuple[str, ...] = ("SOXL", "BEX", "TQQQ", "IRE", "IONL", "DRAM")
    ema_period: int = 20
    sma_period: int = 50
    rsi_period: int = 14
    volume_period: int = 20
    entry_rsi_min: float = 45.0
    entry_rsi_max: float = 65.0
    initial_stop_percent: float = 0.10
    break_even_trigger: float = 0.15
    tight_trailing_trigger: float = 0.20
    tight_trailing_percent: float = 0.05
    wide_trailing_trigger: float = 0.30
    wide_trailing_percent: float = 0.10
    reentry_rsi_max: float = 55.0
    ema_near_tolerance: float = 0.02
    max_risk_per_trade: float = 0.01
    max_position_percent: float = 0.20
    underlying_exposure_map: tuple[tuple[str, str], ...] = (
        ("NBIS", "NEBX"),
        ("IREN", "IREN"),
        ("BE", "BE"),
    )
    earnings_entry_blackout_days: int = 5
    earnings_forced_exit_days: int = 1
    earnings_post_wait_days: int = 2
    earnings_safe_haven_symbol: str = "SGOV"

    def __post_init__(self) -> None:
        periods = (self.ema_period, self.sma_period, self.rsi_period, self.volume_period)
        if any(period <= 0 for period in periods):
            raise ValueError("indicator periods must be positive")
        if not 0 <= self.entry_rsi_min <= self.entry_rsi_max <= 100:
            raise ValueError("entry RSI bounds must be between 0 and 100")
        percentages = (
            self.initial_stop_percent,
            self.max_risk_per_trade,
            self.max_position_percent,
        )
        if any(value <= 0 or value >= 1 for value in percentages):
            raise ValueError("risk, stop, and position percentages must be between 0 and 1")
        if self.earnings_forced_exit_days > self.earnings_entry_blackout_days:
            raise ValueError("forced earnings exit must occur inside the entry blackout window")
        if any(value < 0 for value in (
            self.earnings_entry_blackout_days,
            self.earnings_forced_exit_days,
            self.earnings_post_wait_days,
        )):
            raise ValueError("earnings protection day counts cannot be negative")

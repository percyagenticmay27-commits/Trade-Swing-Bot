"""Provider-neutral models for paper-only daily market data refresh."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal
from math import isfinite
from typing import Any


@dataclass(frozen=True, slots=True)
class DailyMarketBar:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: int

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        values = {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "adjusted_close": self.adjusted_close,
        }
        for name, value in values.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError, OverflowError):
                errors.append(f"{name} must be numeric")
                continue
            if not isfinite(numeric) or value <= 0:
                errors.append(f"{name} must be finite and greater than zero")
        if self.volume < 0:
            errors.append("volume must be greater than or equal to zero")
        if self.high < max(self.open, self.low, self.close):
            errors.append("high must be at least open, low, and close")
        if self.low > min(self.open, self.high, self.close):
            errors.append("low must be no greater than open, high, and close")
        return tuple(errors)


@dataclass(frozen=True, slots=True)
class SymbolRequest:
    symbol: str
    required: bool
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderFetchResult:
    symbol: str
    provider: str
    bars: tuple[DailyMarketBar, ...]
    requested_at_utc: str
    completed_at_utc: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SymbolRefreshResult:
    symbol: str
    required: bool
    fetch_status: str
    validation_status: str
    publication_status: str
    output_path: str
    bar_count: int
    latest_completed_date: str | None
    freshness_status: str
    prior_file_preserved: bool
    provider_attempts: tuple[dict[str, Any], ...] = ()
    selected_provider: str | None = None
    adjusted_close_source: str = "UNAVAILABLE"
    corporate_action_adjusted: bool = False
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["provider_attempts"] = [dict(item) for item in self.provider_attempts]
        payload["warnings"] = list(self.warnings)
        payload["errors"] = list(self.errors)
        return payload


@dataclass(frozen=True, slots=True)
class MarketDataRefreshReport:
    generated_at: str
    provider: str
    requested_symbols: tuple[str, ...]
    required_symbols: tuple[str, ...]
    optional_symbols: tuple[str, ...]
    successful_symbols: tuple[str, ...]
    failed_symbols: tuple[str, ...]
    target_completed_bars: int
    minimum_compatible_bars: int
    symbol_results: tuple[SymbolRefreshResult, ...]
    overall_status: str
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    paper_trade_mode: bool = True
    live_trading_enabled: bool = False
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.1",
            "generated_at": self.generated_at,
            "provider": self.provider,
            "overall_status": self.overall_status,
            "requested_symbols": list(self.requested_symbols),
            "required_symbols": list(self.required_symbols),
            "optional_symbols": list(self.optional_symbols),
            "successful_symbols": list(self.successful_symbols),
            "failed_symbols": list(self.failed_symbols),
            "target_completed_bars": self.target_completed_bars,
            "minimum_compatible_bars": self.minimum_compatible_bars,
            "symbol_results": [item.to_dict() for item in self.symbol_results],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "paper_trade_mode": self.paper_trade_mode,
            "live_trading_enabled": self.live_trading_enabled,
            "broker_execution_enabled": self.broker_execution_enabled,
            "order_placement_enabled": self.order_placement_enabled,
        }

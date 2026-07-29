"""Provider boundary for server-ready paper market data."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence, runtime_checkable

from .market_data_models import DailyMarketBar


class MarketDataProviderError(RuntimeError):
    """Controlled provider failure that must not alter prior valid CSV files."""


@runtime_checkable
class MarketDataProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    def fetch_daily_bars(
        self,
        symbol: str,
        *,
        target_completed_bars: int,
        as_of_utc: datetime,
    ) -> Sequence[DailyMarketBar]: ...

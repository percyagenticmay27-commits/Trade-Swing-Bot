"""YFINANCE implementation of the provider-neutral market-data contract."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Sequence

from ..market_data_models import DailyMarketBar
from ..market_data_provider import MarketDataProviderError


class YFinanceProvider:
    """Fetch unadjusted daily OHLCV while retaining adjusted close separately."""

    @property
    def provider_name(self) -> str:
        return "YFINANCE"

    def fetch_daily_bars(
        self,
        symbol: str,
        *,
        target_completed_bars: int,
        as_of_utc: datetime,
    ) -> Sequence[DailyMarketBar]:
        del as_of_utc
        try:
            import yfinance as yf
        except ImportError as exc:
            raise MarketDataProviderError(
                "yfinance is not installed; install the project market-data dependency"
            ) from exc

        period = "2y" if target_completed_bars <= 400 else "5y"
        try:
            frame = yf.Ticker(symbol).history(
                period=period,
                interval="1d",
                auto_adjust=False,
                actions=False,
                repair=True,
            )
        except Exception as exc:  # provider exceptions vary by release
            raise MarketDataProviderError(f"YFINANCE fetch failed for {symbol}: {exc}") from exc
        if frame is None or frame.empty:
            raise MarketDataProviderError(f"YFINANCE returned no daily bars for {symbol}")

        bars: list[DailyMarketBar] = []
        for index, row in frame.iterrows():
            try:
                bar_date = index.date()
                adjusted = row.get("Adj Close", row.get("Close"))
                bars.append(
                    DailyMarketBar(
                        date=bar_date,
                        open=_decimal(row.get("Open")),
                        high=_decimal(row.get("High")),
                        low=_decimal(row.get("Low")),
                        close=_decimal(row.get("Close")),
                        adjusted_close=_decimal(adjusted),
                        volume=int(row.get("Volume")),
                    )
                )
            except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
                raise MarketDataProviderError(
                    f"YFINANCE returned an invalid row for {symbol} on {index}: {exc}"
                ) from exc
        return tuple(bars)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))

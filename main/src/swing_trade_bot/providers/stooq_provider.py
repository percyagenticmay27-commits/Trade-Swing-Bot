"""Read-only Stooq daily historical data provider.

Stooq is used only as a secondary historical-bar source. It performs no broker,
account, or order operations. Stooq does not provide a distinct adjusted-close
field in this CSV interface, so Close is explicitly copied to adjusted_close and
disclosed through provider metadata.
"""
from __future__ import annotations

import csv
import io
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable, Sequence

from ..market_data_models import DailyMarketBar
from ..market_data_provider import MarketDataProviderError

STOOQ_BASE_URL = "https://stooq.com/q/d/l/"


class StooqProviderError(MarketDataProviderError):
    def __init__(self, message: str, classification: str = "NETWORK_FAILURE") -> None:
        super().__init__(message)
        self.classification = classification


Downloader = Callable[[str, int], bytes]


def _download(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Trade-Swing-Bot/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        classification = "RATE_LIMIT" if exc.code == 429 else "NETWORK_FAILURE"
        raise StooqProviderError(f"Stooq HTTP {exc.code}", classification) from exc
    except urllib.error.URLError as exc:
        raise StooqProviderError(f"Stooq network failure: {exc.reason}") from exc


class StooqProvider:
    """Fetch completed US-equity daily OHLCV history from Stooq CSV."""

    adjusted_close_source = "UNAVAILABLE_USE_CLOSE"
    corporate_action_adjusted = False

    def __init__(self, downloader: Downloader = _download, timeout: int = 30) -> None:
        self._downloader = downloader
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return "STOOQ_READ_ONLY"

    def fetch_daily_bars(
        self,
        symbol: str,
        *,
        target_completed_bars: int,
        as_of_utc: datetime,
    ) -> Sequence[DailyMarketBar]:
        mapped = self._map_symbol(symbol)
        url = f"{STOOQ_BASE_URL}?s={mapped}&d1=19000101&d2={as_of_utc:%Y%m%d}&i=d"
        raw = self._downloader(url, self._timeout)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise StooqProviderError("Stooq response is not UTF-8", "PROVIDER_SCHEMA_ERROR") from exc

        reader = csv.DictReader(io.StringIO(text))
        expected = {"Date", "Open", "High", "Low", "Close", "Volume"}
        if not reader.fieldnames or not expected.issubset(set(reader.fieldnames)):
            raise StooqProviderError("Stooq response schema is invalid", "PROVIDER_SCHEMA_ERROR")

        bars: list[DailyMarketBar] = []
        for row_number, row in enumerate(reader, start=2):
            if not row or str(row.get("Date", "")).strip().lower() in {"", "no data"}:
                continue
            try:
                close = Decimal(str(row["Close"]).strip())
                bar = DailyMarketBar(
                    date=date.fromisoformat(str(row["Date"]).strip()),
                    open=Decimal(str(row["Open"]).strip()),
                    high=Decimal(str(row["High"]).strip()),
                    low=Decimal(str(row["Low"]).strip()),
                    close=close,
                    adjusted_close=close,
                    volume=int(Decimal(str(row["Volume"]).strip())),
                )
            except (KeyError, ValueError, InvalidOperation) as exc:
                raise StooqProviderError(
                    f"Invalid Stooq row {row_number}: {exc}", "PROVIDER_SCHEMA_ERROR"
                ) from exc
            if bar.date <= as_of_utc.date():
                bars.append(bar)

        bars.sort(key=lambda item: item.date)
        if not bars:
            raise StooqProviderError(f"Symbol not found at Stooq: {symbol}", "SYMBOL_NOT_FOUND")
        if len(bars) < 51:
            raise StooqProviderError(
                f"Stooq returned only {len(bars)} daily bars for {symbol}",
                "INSUFFICIENT_HISTORY",
            )
        return tuple(bars[-max(target_completed_bars, 51):])

    @staticmethod
    def _map_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized or normalized.startswith("^"):
            raise StooqProviderError(
                f"Stooq symbol mapping required: {symbol}", "SYMBOL_MAPPING_REQUIRED"
            )
        return normalized.lower().replace(".", "-") + ".us"

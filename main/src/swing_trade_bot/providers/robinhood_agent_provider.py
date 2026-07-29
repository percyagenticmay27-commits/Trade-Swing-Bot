"""Read-only Robinhood Agent MCP adapter for historical daily OHLCV.

This module intentionally contains no HTTP client, credentials, account mutation,
order placement, cancellation, transfer, position-management, or execution logic.
The connected runtime must inject a callable that invokes the verified MCP operation:

mcp__codex_apps__robinhood_etf_tradebot_get_equity_historicals
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Sequence

from ..market_data_models import DailyMarketBar
from ..market_data_provider import MarketDataProviderError

ROBINHOOD_OPERATION = "mcp__codex_apps__robinhood_etf_tradebot_get_equity_historicals"
MAX_SYMBOLS_PER_CALL = 10


class RobinhoodAgentProviderError(MarketDataProviderError):
    """Controlled read-only Robinhood market-data failure."""

    def __init__(self, classification: str, message: str) -> None:
        self.classification = classification
        super().__init__(f"{classification}: {message}")


McpInvoker = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


class RobinhoodAgentReadOnlyProvider:
    """Fetch daily OHLCV through the connected read-only Robinhood MCP tool."""

    adjusted_close_source = "UNAVAILABLE_USE_CLOSE"
    corporate_action_adjusted = False

    def __init__(self, invoke_mcp: McpInvoker) -> None:
        if not callable(invoke_mcp):
            raise TypeError("invoke_mcp must be callable")
        self._invoke_mcp = invoke_mcp

    @property
    def provider_name(self) -> str:
        return "ROBINHOOD_AGENT_READ_ONLY"

    def fetch_daily_bars(
        self,
        symbol: str,
        *,
        target_completed_bars: int,
        as_of_utc: datetime,
    ) -> Sequence[DailyMarketBar]:
        symbol = str(symbol).strip().upper()
        if not symbol:
            raise RobinhoodAgentProviderError("SYMBOL_MAPPING_REQUIRED", "symbol is empty")

        # Request enough calendar history to cover the target number of sessions.
        lookback_days = max(400, int(target_completed_bars * 1.8))
        start = (as_of_utc.astimezone(timezone.utc) - timedelta(days=lookback_days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = as_of_utc.astimezone(timezone.utc).replace(microsecond=0)
        request = {
            "symbols": [symbol],
            "start_time": start.isoformat().replace("+00:00", "Z"),
            "end_time": end.isoformat().replace("+00:00", "Z"),
            "interval": "day",
            "bounds": "regular",
            "adjustment_type": "split",
        }

        try:
            response = self._invoke_mcp(ROBINHOOD_OPERATION, request)
        except Exception as exc:
            raise RobinhoodAgentProviderError(_classify_exception(exc), str(exc)) from exc

        return _parse_response(response, symbol)


def _parse_response(response: Mapping[str, Any], symbol: str) -> tuple[DailyMarketBar, ...]:
    if not isinstance(response, Mapping):
        raise RobinhoodAgentProviderError("PROVIDER_SCHEMA_ERROR", "response root must be an object")
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise RobinhoodAgentProviderError("PROVIDER_SCHEMA_ERROR", "response.data must be an object")

    not_found = data.get("not_found", [])
    if isinstance(not_found, Sequence) and not isinstance(not_found, (str, bytes)):
        if symbol in {str(item).upper() for item in not_found}:
            raise RobinhoodAgentProviderError("SYMBOL_NOT_FOUND", f"{symbol} was returned in not_found")

    results = data.get("results")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise RobinhoodAgentProviderError("PROVIDER_SCHEMA_ERROR", "response.data.results must be an array")

    match: Mapping[str, Any] | None = None
    for item in results:
        if isinstance(item, Mapping) and str(item.get("symbol", "")).upper() == symbol:
            match = item
            break
    if match is None:
        raise RobinhoodAgentProviderError("SYMBOL_NOT_FOUND", f"no result returned for {symbol}")
    if match.get("interval") != "day" or match.get("bounds") != "regular":
        raise RobinhoodAgentProviderError(
            "PROVIDER_SCHEMA_ERROR", "result interval/bounds do not match day/regular"
        )

    raw_bars = match.get("bars")
    if not isinstance(raw_bars, Sequence) or isinstance(raw_bars, (str, bytes)):
        raise RobinhoodAgentProviderError("PROVIDER_SCHEMA_ERROR", "result.bars must be an array")

    bars: list[DailyMarketBar] = []
    for raw in raw_bars:
        if not isinstance(raw, Mapping):
            raise RobinhoodAgentProviderError("PROVIDER_SCHEMA_ERROR", "bar must be an object")
        if raw.get("interpolated") is True:
            continue
        try:
            begins_at = str(raw["begins_at"])
            bar_date = datetime.fromisoformat(begins_at.replace("Z", "+00:00")).date()
            close = Decimal(str(raw["close_price"]))
            bar = DailyMarketBar(
                date=bar_date,
                open=Decimal(str(raw["open_price"])),
                high=Decimal(str(raw["high_price"])),
                low=Decimal(str(raw["low_price"])),
                close=close,
                adjusted_close=close,
                volume=int(raw["volume"]),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            raise RobinhoodAgentProviderError(
                "PROVIDER_SCHEMA_ERROR", f"invalid bar for {symbol}: {exc}"
            ) from exc
        validation_errors = bar.validate()
        if validation_errors:
            raise RobinhoodAgentProviderError(
                "CORPORATE_ACTION_CONFLICT",
                f"invalid OHLCV for {symbol} on {bar.date}: {'; '.join(validation_errors)}",
            )
        bars.append(bar)

    if not bars:
        raise RobinhoodAgentProviderError("INSUFFICIENT_HISTORY", f"no usable daily bars for {symbol}")
    return tuple(bars)


def _classify_exception(exc: Exception) -> str:
    message = str(exc).lower()
    if "rate" in message and "limit" in message:
        return "RATE_LIMIT"
    if any(token in message for token in ("network", "timeout", "connection", "unavailable")):
        return "NETWORK_FAILURE"
    if "not found" in message:
        return "SYMBOL_NOT_FOUND"
    return "NETWORK_FAILURE"

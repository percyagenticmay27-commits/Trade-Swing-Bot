"""Build deterministic, read-only market-data provider chains.

Version 1.1 order:
YFINANCE -> STOOQ_READ_ONLY -> ROBINHOOD_AGENT_READ_ONLY -> prior local CSV.
The prior CSV fallback remains owned by market_data_refresh publication logic.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .market_data_provider_chain import MarketDataProviderChain
from .providers.robinhood_agent_provider import McpInvoker, RobinhoodAgentReadOnlyProvider
from .providers.stooq_provider import StooqProvider
from .providers.yfinance_provider import YFinanceProvider

SUPPORTED_PROVIDERS = (
    "YFINANCE",
    "STOOQ_READ_ONLY",
    "ROBINHOOD_AGENT_READ_ONLY",
)
DEFAULT_PROVIDER_ORDER = SUPPORTED_PROVIDERS


def build_configured_provider_chain(
    *,
    config: Mapping[str, Any] | None = None,
    invoke_mcp: McpInvoker | None = None,
) -> MarketDataProviderChain:
    payload = dict(config or {})
    raw_order = payload.get("provider_order", DEFAULT_PROVIDER_ORDER)
    if not isinstance(raw_order, Sequence) or isinstance(raw_order, (str, bytes)):
        raise ValueError("provider_order must be a list")
    order = tuple(str(item).strip().upper() for item in raw_order)
    if not order:
        raise ValueError("provider_order must not be empty")
    unknown = [name for name in order if name not in SUPPORTED_PROVIDERS]
    if unknown:
        raise ValueError("unsupported market-data providers: " + ", ".join(unknown))
    if len(order) != len(set(order)):
        raise ValueError("provider_order must contain unique names")

    providers = []
    for name in order:
        if name == "YFINANCE":
            providers.append(YFinanceProvider())
        elif name == "STOOQ_READ_ONLY":
            providers.append(StooqProvider())
        elif name == "ROBINHOOD_AGENT_READ_ONLY":
            if invoke_mcp is None:
                # A normal shell process cannot invent or directly call the MCP tool.
                # Excluding it here is safer than claiming the fallback is available.
                continue
            providers.append(RobinhoodAgentReadOnlyProvider(invoke_mcp))

    if not providers:
        raise ValueError("no runnable market-data providers are configured")
    return MarketDataProviderChain(tuple(providers))

import pytest

from swing_trade_bot.market_data_chain_factory import build_configured_provider_chain


def test_default_chain_uses_free_historical_providers_without_mcp():
    chain = build_configured_provider_chain()
    assert chain.provider_names == ("YFINANCE", "STOOQ_READ_ONLY")
    assert chain.provider_name == "YFINANCE->STOOQ_READ_ONLY->PRIOR_LOCAL_CSV"


def test_robinhood_is_added_only_when_runtime_supplies_mcp_invoker():
    def invoke(_operation: str, _payload: dict):
        return {"data": {"results": [], "not_found": []}}

    chain = build_configured_provider_chain(invoke_mcp=invoke)
    assert chain.provider_names == (
        "YFINANCE",
        "STOOQ_READ_ONLY",
        "ROBINHOOD_AGENT_READ_ONLY",
    )


def test_provider_order_is_configurable_and_unique():
    chain = build_configured_provider_chain(
        config={"provider_order": ["STOOQ_READ_ONLY", "YFINANCE"]}
    )
    assert chain.provider_names == ("STOOQ_READ_ONLY", "YFINANCE")

    with pytest.raises(ValueError, match="unique"):
        build_configured_provider_chain(
            config={"provider_order": ["YFINANCE", "YFINANCE"]}
        )


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        build_configured_provider_chain(config={"provider_order": ["UNKNOWN"]})

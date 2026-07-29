from datetime import datetime, timezone

import pytest

from swing_trade_bot.market_data_provider import MarketDataProvider, MarketDataProviderError
from swing_trade_bot.providers.yfinance_provider import YFinanceProvider


def test_yfinance_provider_name():
    assert YFinanceProvider().provider_name == "YFINANCE"


def test_yfinance_provider_matches_protocol():
    assert isinstance(YFinanceProvider(), MarketDataProvider)


def test_provider_does_not_expose_order_methods():
    provider = YFinanceProvider()
    assert not hasattr(provider, "place_order")
    assert not hasattr(provider, "review_order")


def test_missing_yfinance_is_controlled(monkeypatch):
    import builtins
    original = builtins.__import__
    def blocked(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("missing")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(MarketDataProviderError):
        YFinanceProvider().fetch_daily_bars("SPY", target_completed_bars=250, as_of_utc=datetime.now(timezone.utc))

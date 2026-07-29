from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from swing_trade_bot.market_data_models import DailyMarketBar
from swing_trade_bot.market_data_provider import MarketDataProviderError
from swing_trade_bot.market_data_provider_chain import MarketDataProviderChain
from swing_trade_bot.market_data_refresh import refresh_market_data
from swing_trade_bot.providers.robinhood_agent_provider import (
    ROBINHOOD_OPERATION,
    RobinhoodAgentReadOnlyProvider,
)


NOW = datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc)


def _bars(count=250):
    dates = []
    current = NOW.date()
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current -= timedelta(days=1)
    dates.reverse()
    return tuple(
        DailyMarketBar(item, Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), Decimal("11"), 1000)
        for item in dates
    )


class FakeProvider:
    def __init__(self, name, bars=(), error=None):
        self._name = name
        self._bars = tuple(bars)
        self._error = error
        self.calls = 0

    @property
    def provider_name(self):
        return self._name

    def fetch_daily_bars(self, symbol, *, target_completed_bars, as_of_utc):
        self.calls += 1
        if self._error:
            raise MarketDataProviderError(self._error)
        return self._bars


def _config(**changes):
    payload = {
        "market_data_schema_version": "1.0",
        "provider": "PROVIDER_CHAIN",
        "data_directory": "data",
        "target_completed_bars": 250,
        "minimum_compatible_bars": 51,
        "configured_strategy_symbols": ["SOXL"],
        "portfolio_symbols": [],
        "watchlist_symbols": [],
        "candidate_symbols": [],
        "exchange_timezone": "America/New_York",
        "market_close_time": "16:00",
        "settlement_buffer_minutes": 30,
        "freshness": {"warning_after_completed_sessions": 1, "stale_after_completed_sessions": 3},
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "ai_cio_market_data_owner": False,
    }
    payload.update(changes)
    return payload


def _robinhood_response(symbol="SPY", count=250, interpolated_first=False):
    bars = []
    for index, bar in enumerate(_bars(count)):
        bars.append({
            "begins_at": f"{bar.date.isoformat()}T00:00:00Z",
            "open_price": str(bar.open),
            "high_price": str(bar.high),
            "low_price": str(bar.low),
            "close_price": str(bar.close),
            "volume": bar.volume,
            "session": "reg",
            "interpolated": interpolated_first and index == 0,
        })
    return {"data": {"results": [{"symbol": symbol, "interval": "day", "bounds": "regular", "bars": bars}], "not_found": []}}


def test_yahoo_success_prevents_robinhood_call():
    yahoo = FakeProvider("YFINANCE", _bars())
    robinhood = FakeProvider("ROBINHOOD_AGENT_READ_ONLY", _bars())
    result = MarketDataProviderChain((yahoo, robinhood)).fetch_daily_bars("SPY", target_completed_bars=250, as_of_utc=NOW)
    assert result.selected_provider == "YFINANCE"
    assert yahoo.calls == 1
    assert robinhood.calls == 0


def test_yahoo_failure_invokes_robinhood():
    yahoo = FakeProvider("YFINANCE", error="failed")
    robinhood = FakeProvider("ROBINHOOD_AGENT_READ_ONLY", _bars())
    result = MarketDataProviderChain((yahoo, robinhood)).fetch_daily_bars("SPY", target_completed_bars=250, as_of_utc=NOW)
    assert result.selected_provider == "ROBINHOOD_AGENT_READ_ONLY"
    assert yahoo.calls == 1
    assert robinhood.calls == 1


def test_robinhood_adapter_normalizes_and_discloses_adjustment():
    calls = []
    def invoke(operation, request):
        calls.append((operation, request))
        return _robinhood_response()
    provider = RobinhoodAgentReadOnlyProvider(invoke)
    bars = provider.fetch_daily_bars("SPY", target_completed_bars=250, as_of_utc=NOW)
    assert calls[0][0] == ROBINHOOD_OPERATION
    assert calls[0][1]["symbols"] == ["SPY"]
    assert calls[0][1]["interval"] == "day"
    assert calls[0][1]["bounds"] == "regular"
    assert calls[0][1]["adjustment_type"] == "split"
    assert len(bars) == 250
    assert bars[-1].adjusted_close == bars[-1].close
    assert provider.adjusted_close_source == "UNAVAILABLE_USE_CLOSE"
    assert provider.corporate_action_adjusted is False


def test_interpolated_bars_are_ignored():
    provider = RobinhoodAgentReadOnlyProvider(lambda operation, request: _robinhood_response(interpolated_first=True))
    bars = provider.fetch_daily_bars("SPY", target_completed_bars=250, as_of_utc=NOW)
    assert len(bars) == 249


def test_robinhood_success_publishes_and_reports_provider(tmp_path: Path):
    yahoo = FakeProvider("YFINANCE", error="failed")
    robinhood = RobinhoodAgentReadOnlyProvider(lambda operation, request: _robinhood_response(request["symbols"][0]))
    chain = MarketDataProviderChain((yahoo, robinhood))
    report = refresh_market_data(_config(), chain, project_root=tmp_path, as_of_utc=NOW)
    assert report.failed_symbols == ()
    for result in report.symbol_results:
        assert result.selected_provider == "ROBINHOOD_AGENT_READ_ONLY"
        assert result.publication_status == "PUBLISHED"
        assert result.adjusted_close_source == "UNAVAILABLE_USE_CLOSE"
        assert result.corporate_action_adjusted is False
        assert (tmp_path / "data" / f"{result.symbol}.csv").exists()


def test_all_provider_failure_uses_prior_file(tmp_path: Path):
    good = FakeProvider("YFINANCE", _bars())
    refresh_market_data(_config(), good, project_root=tmp_path, as_of_utc=NOW)
    chain = MarketDataProviderChain((FakeProvider("YFINANCE", error="failed"), FakeProvider("ROBINHOOD_AGENT_READ_ONLY", error="failed")))
    report = refresh_market_data(_config(), chain, project_root=tmp_path, as_of_utc=NOW)
    assert report.failed_symbols == ()
    assert all(item.selected_provider == "PRIOR_LOCAL_CSV" for item in report.symbol_results)
    assert all(item.publication_status == "PRESERVED_PRIOR_VALID_FILE" for item in report.symbol_results)


def test_required_symbol_blocks_only_after_all_sources_fail(tmp_path: Path):
    chain = MarketDataProviderChain((FakeProvider("YFINANCE", error="failed"), FakeProvider("ROBINHOOD_AGENT_READ_ONLY", error="failed")))
    report = refresh_market_data(_config(), chain, project_root=tmp_path, as_of_utc=NOW)
    assert report.overall_status == "BLOCKED"
    assert "SPY" in report.failed_symbols


def test_adapter_exposes_no_mutation_or_order_methods():
    names = {name.lower() for name in dir(RobinhoodAgentReadOnlyProvider)}
    forbidden = ("order", "cancel", "transfer", "position", "execute", "buy", "sell")
    assert not any(any(word in name for word in forbidden) for name in names)

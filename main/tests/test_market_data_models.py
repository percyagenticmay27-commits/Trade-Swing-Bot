from datetime import date
from decimal import Decimal

from swing_trade_bot.market_data_models import DailyMarketBar, MarketDataRefreshReport, SymbolRefreshResult


def bar(**changes):
    values = dict(date=date(2026, 7, 28), open=Decimal("10"), high=Decimal("12"), low=Decimal("9"), close=Decimal("11"), adjusted_close=Decimal("11"), volume=100)
    values.update(changes)
    return DailyMarketBar(**values)


def test_valid_bar():
    assert bar().validate() == ()


def test_negative_price_rejected():
    assert any("open" in item for item in bar(open=Decimal("-1")).validate())


def test_invalid_high_rejected():
    assert any("high" in item for item in bar(high=Decimal("10")).validate())


def test_negative_volume_rejected():
    assert any("volume" in item for item in bar(volume=-1).validate())


def test_refresh_result_keeps_separate_statuses():
    result = SymbolRefreshResult("SPY", True, "SUCCESS", "PASSED", "PUBLISHED", "data/SPY.csv", 250, "2026-07-28", "FRESH", False)
    payload = result.to_dict()
    assert payload["fetch_status"] == "SUCCESS"
    assert payload["validation_status"] == "PASSED"
    assert payload["publication_status"] == "PUBLISHED"


def test_report_safety_values():
    report = MarketDataRefreshReport("2026-07-29T00:00:00Z", "YFINANCE", (), (), (), (), (), 250, 51, (), "READY", (), ())
    payload = report.to_dict()
    assert payload["paper_trade_mode"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["broker_execution_enabled"] is False

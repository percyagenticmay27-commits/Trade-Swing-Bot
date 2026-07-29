from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from swing_trade_bot.market_data_models import DailyMarketBar
from swing_trade_bot.market_data_refresh import (
    normalize_daily_bars,
    refresh_market_data,
    resolve_symbol_requests,
    validate_market_data_config,
)


class FakeProvider:
    provider_name = "YFINANCE"
    def __init__(self, failures=()):
        self.failures = set(failures)
    def fetch_daily_bars(self, symbol, *, target_completed_bars, as_of_utc):
        if symbol in self.failures:
            raise ValueError("provider failure")
        start = date(2025, 7, 1)
        return tuple(
            DailyMarketBar(start + timedelta(days=i), Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), Decimal("11"), 1000)
            for i in range(target_completed_bars + 120)
            if (start + timedelta(days=i)).weekday() < 5
        )


def config(**changes):
    payload = {
        "market_data_schema_version": "1.0", "provider": "YFINANCE", "data_directory": "data",
        "target_completed_bars": 250, "minimum_compatible_bars": 51,
        "configured_strategy_symbols": ["SOXL"], "portfolio_symbols": ["AMD"],
        "watchlist_symbols": ["MSFT"], "candidate_symbols": ["NVDA"],
        "exchange_timezone": "America/New_York", "market_close_time": "16:00",
        "settlement_buffer_minutes": 30,
        "freshness": {"warning_after_completed_sessions": 1, "stale_after_completed_sessions": 3},
        "paper_trade_mode": True, "live_trading_enabled": False,
        "broker_execution_enabled": False, "ai_cio_market_data_owner": False,
    }
    payload.update(changes)
    return payload


def test_config_valid():
    assert validate_market_data_config(config()).valid


def test_safety_lock_rejected():
    assert not validate_market_data_config(config(broker_execution_enabled=True)).valid


def test_symbol_resolution_required_wins():
    requests = resolve_symbol_requests(configured_strategy_symbols=["soxl"], portfolio_symbols=["amd"], watchlist_symbols=["amd"], candidate_symbols=["nvda"])
    by_symbol = {item.symbol: item for item in requests}
    assert tuple(by_symbol) == ("SPY", "QQQ", "SOXL", "AMD", "NVDA")
    assert by_symbol["AMD"].required is True
    assert by_symbol["NVDA"].required is False


def test_current_day_excluded_before_buffer():
    today = date(2026, 7, 29)
    bars = [DailyMarketBar(today, Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), Decimal("11"), 100)]
    result = normalize_daily_bars(bars, as_of_utc=datetime(2026, 7, 29, 19, 0, tzinfo=timezone.utc), exchange_timezone="America/New_York", market_close_time=datetime.strptime("16:00", "%H:%M").time(), settlement_buffer_minutes=30)
    assert result == ()


def test_current_day_allowed_after_buffer():
    today = date(2026, 7, 29)
    bar = DailyMarketBar(today, Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), Decimal("11"), 100)
    result = normalize_daily_bars([bar], as_of_utc=datetime(2026, 7, 29, 21, 0, tzinfo=timezone.utc), exchange_timezone="America/New_York", market_close_time=datetime.strptime("16:00", "%H:%M").time(), settlement_buffer_minutes=30)
    assert result == (bar,)


def test_required_failure_blocks(tmp_path: Path):
    report = refresh_market_data(config(), FakeProvider({"SPY"}), project_root=tmp_path, as_of_utc=datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc))
    assert report.overall_status == "BLOCKED"
    assert "SPY" in report.failed_symbols


def test_optional_failure_warns(tmp_path: Path):
    report = refresh_market_data(config(), FakeProvider({"NVDA"}), project_root=tmp_path, as_of_utc=datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc))
    assert report.overall_status == "READY_WITH_WARNINGS"
    assert "NVDA" in report.failed_symbols
    assert (tmp_path / "data" / "SPY.csv").exists()


def test_failed_refresh_preserves_prior_valid_file(tmp_path: Path):
    now = datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc)
    first = refresh_market_data(config(watchlist_symbols=[], candidate_symbols=[]), FakeProvider(), project_root=tmp_path, as_of_utc=now)
    assert first.overall_status in {"READY", "READY_WITH_WARNINGS"}
    original = (tmp_path / "data" / "SPY.csv").read_bytes()
    second = refresh_market_data(config(watchlist_symbols=[], candidate_symbols=[]), FakeProvider({"SPY"}), project_root=tmp_path, as_of_utc=now)
    result = next(item for item in second.symbol_results if item.symbol == "SPY")
    assert result.publication_status == "PRESERVED_PRIOR_VALID_FILE"
    assert (tmp_path / "data" / "SPY.csv").read_bytes() == original

import json
from pathlib import Path

import pytest

from swing_trade_bot.enterprise_market_data_client import EnterpriseQuote, MarketDataUnavailable
from swing_trade_bot.enterprise_paper_portfolio_manager import (
    SWING_ALLOCATION,
    build_enterprise_paper_portfolio_report,
)


class StubClient:
    def __init__(self, prices): self.prices = prices
    def get_quote(self, symbol, required=True):
        if symbol not in self.prices:
            raise MarketDataUnavailable(f"{symbol} missing")
        return EnterpriseQuote(
            symbol=symbol, price=self.prices[symbol],
            quote_timestamp="2026-08-04T20:00:00+00:00",
            trading_date="2026-08-04", provider="ANY_PROVIDER",
            source_type="NORMALIZED_QUOTE", confidence=0.9,
        )


def _ledger(tmp_path: Path) -> Path:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "open_positions.json").write_text(json.dumps({"positions": [
        {"symbol": "SOXL", "entry_date": "2026-06-22", "entry_price": 100.0, "shares": 10.0, "cost_basis": 1000.0, "allocation_percent": 22.2222, "active_strategy": "Strategy A"},
        {"symbol": "TQQQ", "entry_date": "2026-06-22", "entry_price": 50.0, "shares": 10.0, "cost_basis": 500.0, "allocation_percent": 11.1111, "active_strategy": "Strategy A"},
    ]}), encoding="utf-8")
    return ledger


def test_fresh_enterprise_quotes_drive_existing_formulas(tmp_path):
    report = build_enterprise_paper_portfolio_report(
        ledger_dir=_ledger(tmp_path), account_capital=4500.0,
        client=StubClient({"SOXL": 140.0, "TQQQ": 45.0}),
    )
    assert report.invested_capital == 1500.0
    assert report.cash_balance == 3000.0
    assert report.positions_market_value == 1850.0
    assert report.portfolio_value == 4850.0
    assert report.unrealized_pnl == 350.0
    assert report.portfolio_return_percent == pytest.approx(7.777778)
    soxl = next(item for item in report.positions if item.symbol == "SOXL")
    assert soxl.entry_price == 100.0
    assert soxl.current_price == 140.0
    assert soxl.market_value == 1400.0
    assert soxl.unrealized_pnl == 400.0
    assert soxl.price_source == "ENTERPRISE_NORMALIZED_QUOTE"


def test_entry_price_is_never_used_when_quote_missing(tmp_path):
    with pytest.raises(MarketDataUnavailable):
        build_enterprise_paper_portfolio_report(
            ledger_dir=_ledger(tmp_path), account_capital=4500.0,
            client=StubClient({"SOXL": 140.0}),
        )


def test_swing_allocation_is_locked(tmp_path):
    assert SWING_ALLOCATION == 4500.0
    with pytest.raises(ValueError, match="4500"):
        build_enterprise_paper_portfolio_report(
            ledger_dir=_ledger(tmp_path), account_capital=10000.0,
            client=StubClient({"SOXL": 140.0, "TQQQ": 45.0}),
        )


def test_provider_identity_does_not_change_calculation(tmp_path):
    first = build_enterprise_paper_portfolio_report(
        ledger_dir=_ledger(tmp_path), account_capital=4500.0,
        client=StubClient({"SOXL": 140.0, "TQQQ": 45.0}),
    )
    second = build_enterprise_paper_portfolio_report(
        ledger_dir=_ledger(tmp_path), account_capital=4500.0,
        client=StubClient({"SOXL": 140.0, "TQQQ": 45.0}),
    )
    assert first.portfolio_value == second.portfolio_value

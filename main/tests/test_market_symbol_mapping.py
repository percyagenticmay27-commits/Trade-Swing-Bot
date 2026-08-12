from datetime import date

import pytest

from swing_trade_bot.market_symbol_mapping import (
    get_market_symbol_mapping,
    known_inception_date,
    resolve_symbol,
)


def test_bex_preserves_trade_and_valuation_symbol_but_uses_be_for_signals():
    mapping = get_market_symbol_mapping("BEX")
    assert mapping.trade_symbol == "BEX"
    assert mapping.valuation_symbol == "BEX"
    assert mapping.signal_symbol == "BE"
    assert mapping.earnings_symbol == "BE"
    assert resolve_symbol("BEX", "VALUATION") == "BEX"
    assert resolve_symbol("BEX", "TECHNICAL_SIGNAL") == "BE"


def test_ire_uses_verified_iren_underlying_for_signal_and_earnings():
    assert resolve_symbol("IRE", "VALUATION") == "IRE"
    assert resolve_symbol("IRE", "TECHNICAL_SIGNAL") == "IREN"
    assert resolve_symbol("IRE", "EARNINGS") == "IREN"
    assert known_inception_date("IRE") == date(2025, 10, 20)


def test_ionl_uses_verified_ionq_underlying_without_substituting_valuation():
    assert resolve_symbol("IONL", "VALUATION") == "IONL"
    assert resolve_symbol("IONL", "TECHNICAL_SIGNAL") == "IONQ"
    assert resolve_symbol("IONL", "EARNINGS") == "IONQ"


def test_basket_without_verified_single_underlying_fails_closed_for_signal():
    assert resolve_symbol("DRAM", "VALUATION") == "DRAM"
    with pytest.raises(ValueError, match="SIGNAL_SYMBOL_NOT_CONFIGURED:DRAM"):
        resolve_symbol("DRAM", "TECHNICAL_SIGNAL")


def test_unconfigured_ordinary_symbol_self_maps_without_ticker_guessing():
    mapping = get_market_symbol_mapping("SPY")
    assert mapping.trade_symbol == "SPY"
    assert mapping.valuation_symbol == "SPY"
    assert mapping.signal_symbol == "SPY"
    assert mapping.earnings_symbol == "SPY"

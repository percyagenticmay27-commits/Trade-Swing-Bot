from datetime import date

from swing_trade_bot.data_tools import MINIMUM_BARS, MINIMUM_SIGNAL_BARS, required_bars_for_symbol


def test_mature_symbol_keeps_252_bar_requirement():
    assert required_bars_for_symbol("SOXL", as_of=date(2026, 8, 12)) == MINIMUM_BARS


def test_new_bex_does_not_require_pre_inception_history():
    required = required_bars_for_symbol("BEX", as_of=date(2026, 8, 12))
    assert MINIMUM_SIGNAL_BARS <= required < MINIMUM_BARS
    assert required >= 180


def test_new_ire_does_not_require_pre_inception_history():
    required = required_bars_for_symbol("IRE", as_of=date(2026, 8, 12))
    assert MINIMUM_SIGNAL_BARS <= required < MINIMUM_BARS
    assert required >= 200


def test_dram_recent_launch_uses_realistic_history_requirement():
    required = required_bars_for_symbol("DRAM", as_of=date(2026, 8, 12))
    assert 85 <= required < 110


def test_listing_age_rule_never_drops_below_ema50_evidence_floor():
    required = required_bars_for_symbol("DRAM", as_of=date(2026, 4, 3))
    assert required == MINIMUM_SIGNAL_BARS

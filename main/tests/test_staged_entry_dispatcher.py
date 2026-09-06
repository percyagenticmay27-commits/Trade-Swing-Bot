from pathlib import Path

import pytest

from swing_trade_bot.manual_entry_strategy_registry import EntryRule, ManualEntryStrategy
from swing_trade_bot.staged_entry_dispatcher import (
    acknowledge_completed_entry,
    dispatch_staged_entry,
)
from swing_trade_bot.staged_entry_reservation import release_reservation


def _strategy(entries: int) -> ManualEntryStrategy:
    return ManualEntryStrategy(
        strategy_id="TEST_ENTRY",
        name="Test Entry",
        timeframe="1D",
        rule_logic="ALL",
        rules=(EntryRule("close", ">", "ema", period=20),),
        number_of_entries=entries,
    )


def test_two_entry_strategy_authorizes_one_half_at_a_time() -> None:
    strategy = _strategy(2)
    decision, state = dispatch_staged_entry(
        underlying_symbol="NFLX",
        execution_symbol="NFLU",
        strategy=strategy,
        total_authorized_allocation=500.0,
        entry_stage_qualified=True,
    )
    assert decision.action == "AUTHORIZE_ENTRY"
    assert decision.entry_number == 1
    assert decision.amount_authorized_this_entry == 250.0
    assert state.entries_completed == 0

    state = acknowledge_completed_entry(state)
    decision, unchanged = dispatch_staged_entry(
        underlying_symbol="NFLX",
        execution_symbol="NFLU",
        strategy=strategy,
        total_authorized_allocation=500.0,
        entry_stage_qualified=True,
        reservation=state,
    )
    assert decision.entry_number == 2
    assert decision.amount_authorized_this_entry == 250.0
    assert unchanged.entries_completed == 1


def test_three_entry_strategy_waits_without_consuming_reservation() -> None:
    strategy = _strategy(3)
    decision, state = dispatch_staged_entry(
        underlying_symbol="NVDA",
        execution_symbol="NVDX",
        strategy=strategy,
        total_authorized_allocation=600.0,
        entry_stage_qualified=False,
    )
    assert decision.action == "WAIT"
    assert decision.entry_number == 1
    assert decision.amount_authorized_this_entry == 0.0
    assert state.reserved_allocation == 600.0
    assert state.entries_completed == 0


def test_last_slice_uses_remaining_reserved_amount_for_rounding() -> None:
    strategy = _strategy(3)
    _, state = dispatch_staged_entry(
        underlying_symbol="AMZN",
        execution_symbol="AMZU",
        strategy=strategy,
        total_authorized_allocation=500.0,
        entry_stage_qualified=True,
    )
    state = acknowledge_completed_entry(state)
    state = acknowledge_completed_entry(state)
    decision, _ = dispatch_staged_entry(
        underlying_symbol="AMZN",
        execution_symbol="AMZU",
        strategy=strategy,
        total_authorized_allocation=500.0,
        entry_stage_qualified=True,
        reservation=state,
    )
    assert decision.entry_number == 3
    assert decision.amount_authorized_this_entry == state.reserved_allocation


def test_complete_reservation_cannot_authorize_more_entries() -> None:
    strategy = _strategy(1)
    _, state = dispatch_staged_entry(
        underlying_symbol="PLTR",
        execution_symbol="PLTU",
        strategy=strategy,
        total_authorized_allocation=300.0,
        entry_stage_qualified=True,
    )
    state = acknowledge_completed_entry(state)
    decision, _ = dispatch_staged_entry(
        underlying_symbol="PLTR",
        execution_symbol="PLTU",
        strategy=strategy,
        total_authorized_allocation=300.0,
        entry_stage_qualified=True,
        reservation=state,
    )
    assert decision.action == "COMPLETE"
    assert decision.amount_authorized_this_entry == 0.0


def test_released_reservation_requires_new_allocation_cycle() -> None:
    strategy = _strategy(2)
    _, state = dispatch_staged_entry(
        underlying_symbol="NFLX",
        execution_symbol="NFLU",
        strategy=strategy,
        total_authorized_allocation=500.0,
        entry_stage_qualified=True,
    )
    state = acknowledge_completed_entry(state)
    state = release_reservation(state, reason="POSITION_EXITED")
    decision, _ = dispatch_staged_entry(
        underlying_symbol="NFLX",
        execution_symbol="NFLU",
        strategy=strategy,
        total_authorized_allocation=500.0,
        entry_stage_qualified=True,
        reservation=state,
    )
    assert decision.action == "WAIT"
    assert decision.entry_number is None
    assert decision.amount_authorized_this_entry == 0.0


def test_reservation_must_match_strategy_and_swing_allocation() -> None:
    strategy = _strategy(2)
    _, state = dispatch_staged_entry(
        underlying_symbol="NFLX",
        execution_symbol="NFLU",
        strategy=strategy,
        total_authorized_allocation=500.0,
        entry_stage_qualified=False,
    )
    with pytest.raises(ValueError, match="allocation"):
        dispatch_staged_entry(
            underlying_symbol="NFLX",
            execution_symbol="NFLU",
            strategy=strategy,
            total_authorized_allocation=600.0,
            entry_stage_qualified=True,
            reservation=state,
        )


def test_dispatcher_is_authorization_only_and_paper_only() -> None:
    source = Path("src/swing_trade_bot/staged_entry_dispatcher.py").read_text(encoding="utf-8").lower()
    assert "place_order(" not in source
    assert "sell_order(" not in source
    assert "sgov_movement" not in source
    strategy = _strategy(2)
    decision, _ = dispatch_staged_entry(
        underlying_symbol="NFLX",
        execution_symbol="NFLU",
        strategy=strategy,
        total_authorized_allocation=500.0,
        entry_stage_qualified=True,
    )
    assert decision.paper_trade_mode is True
    assert decision.capital_movement_enabled is False
    assert decision.paper_position_creation_enabled is False
    assert decision.paper_ledger_write_enabled is False

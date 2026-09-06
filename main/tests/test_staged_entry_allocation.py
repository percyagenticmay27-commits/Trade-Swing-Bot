from pathlib import Path

import pytest

from swing_trade_bot.staged_entry_allocation import build_staged_entry_allocation_plan


def test_one_entry_uses_full_swing_allocation() -> None:
    plan = build_staged_entry_allocation_plan(
        underlying_symbol="NFLX",
        execution_symbol="NFLU",
        total_authorized_allocation=500.0,
        number_of_entries=1,
    )

    assert plan.allocation_per_entry == 500.0
    assert plan.deployed_allocation == 0.0
    assert plan.reserved_allocation == 500.0
    assert plan.next_entry_number == 1


def test_two_entries_split_allocation_in_half() -> None:
    plan = build_staged_entry_allocation_plan(
        underlying_symbol="NVDA",
        execution_symbol="NVDX",
        total_authorized_allocation=600.0,
        number_of_entries=2,
        entries_completed=1,
    )

    assert plan.allocation_per_entry == 300.0
    assert plan.deployed_allocation == 300.0
    assert plan.reserved_allocation == 300.0
    assert plan.next_entry_number == 2


def test_three_entries_split_allocation_in_thirds() -> None:
    plan = build_staged_entry_allocation_plan(
        underlying_symbol="AMZN",
        execution_symbol="AMZU",
        total_authorized_allocation=900.0,
        number_of_entries=3,
        entries_completed=2,
    )

    assert plan.allocation_per_entry == 300.0
    assert plan.deployed_allocation == 600.0
    assert plan.reserved_allocation == 300.0
    assert plan.next_entry_number == 3


def test_completed_plan_has_no_reserved_capital() -> None:
    plan = build_staged_entry_allocation_plan(
        underlying_symbol="PLTR",
        execution_symbol="PLTU",
        total_authorized_allocation=450.0,
        number_of_entries=3,
        entries_completed=3,
    )

    assert plan.deployed_allocation == 450.0
    assert plan.reserved_allocation == 0.0
    assert plan.next_entry_number is None


def test_invalid_entry_counts_fail_closed() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        build_staged_entry_allocation_plan(
            underlying_symbol="NFLX",
            execution_symbol="NFLU",
            total_authorized_allocation=500.0,
            number_of_entries=0,
        )
    with pytest.raises(ValueError, match="between 0"):
        build_staged_entry_allocation_plan(
            underlying_symbol="NFLX",
            execution_symbol="NFLU",
            total_authorized_allocation=500.0,
            number_of_entries=2,
            entries_completed=3,
        )


def test_planner_is_paper_only_and_has_no_sgov_or_execution_side_effects() -> None:
    source = Path("src/swing_trade_bot/staged_entry_allocation.py").read_text(
        encoding="utf-8"
    ).lower()

    assert "place_order(" not in source
    assert "paper_ledger" not in source
    assert "sgov" in source  # docs explicitly say this planner does not move SGOV
    assert "create positions" in source

import json
from pathlib import Path

import pytest

from swing_trade_bot.staged_entry_reservation import (
    create_reservation,
    record_completed_entry,
    release_reservation,
    write_reservation_state,
)


def test_two_entry_reservation_tracks_deployed_and_reserved_capital() -> None:
    item = create_reservation(
        underlying_symbol="NFLX",
        execution_symbol="NFLU",
        strategy_id="TEST",
        total_authorized_allocation=500.0,
        number_of_entries=2,
        entries_completed=1,
    )

    assert item.allocation_per_entry == 250.0
    assert item.deployed_allocation == 250.0
    assert item.reserved_allocation == 250.0
    assert item.status == "ACTIVE"


def test_three_entry_reservation_advances_one_slice_at_a_time() -> None:
    item = create_reservation(
        underlying_symbol="NVDA",
        execution_symbol="NVDX",
        strategy_id="TEST",
        total_authorized_allocation=600.0,
        number_of_entries=3,
        entries_completed=1,
    )

    second = record_completed_entry(item)
    assert second.entries_completed == 2
    assert second.deployed_allocation == 400.0
    assert second.reserved_allocation == 200.0
    assert second.status == "ACTIVE"

    third = record_completed_entry(second)
    assert third.entries_completed == 3
    assert third.deployed_allocation == 600.0
    assert third.reserved_allocation == 0.0
    assert third.status == "COMPLETE"


def test_release_returns_undeployed_capital_to_normal_pool_without_touching_deployed() -> None:
    item = create_reservation(
        underlying_symbol="AMZN",
        execution_symbol="AMZU",
        strategy_id="TEST",
        total_authorized_allocation=400.0,
        number_of_entries=2,
        entries_completed=1,
    )

    released = release_reservation(item, reason="POSITION_EXITED_BEFORE_STAGE_2")
    assert released.status == "RELEASED"
    assert released.deployed_allocation == 200.0
    assert released.reserved_allocation == 0.0
    assert released.release_reason == "POSITION_EXITED_BEFORE_STAGE_2"


def test_one_entry_plan_completes_after_first_entry() -> None:
    item = create_reservation(
        underlying_symbol="PLTR",
        execution_symbol="PLTU",
        strategy_id="TEST",
        total_authorized_allocation=350.0,
        number_of_entries=1,
        entries_completed=0,
    )
    completed = record_completed_entry(item)
    assert completed.status == "COMPLETE"
    assert completed.deployed_allocation == 350.0
    assert completed.reserved_allocation == 0.0


def test_invalid_reservation_inputs_fail_closed() -> None:
    with pytest.raises(ValueError):
        create_reservation(
            underlying_symbol="NFLX",
            execution_symbol="NFLU",
            strategy_id="TEST",
            total_authorized_allocation=0.0,
            number_of_entries=2,
        )
    with pytest.raises(ValueError):
        create_reservation(
            underlying_symbol="NFLX",
            execution_symbol="NFLU",
            strategy_id="TEST",
            total_authorized_allocation=500.0,
            number_of_entries=0,
        )


def test_state_write_is_paper_only_and_has_no_capital_or_sgov_side_effects(tmp_path: Path) -> None:
    item = create_reservation(
        underlying_symbol="NFLX",
        execution_symbol="NFLU",
        strategy_id="TEST",
        total_authorized_allocation=500.0,
        number_of_entries=2,
        entries_completed=1,
    )
    path = tmp_path / "staged_entry_reservations.json"
    write_reservation_state(path, (item,))
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["paper_trade_mode"] is True
    assert payload["capital_movement_enabled"] is False
    assert payload["sgov_movement_enabled"] is False
    assert payload["paper_position_creation_enabled"] is False

    source = Path("src/swing_trade_bot/staged_entry_reservation.py").read_text(encoding="utf-8").lower()
    assert "place_order(" not in source
    assert "sell_sgov" not in source
    assert "buy_sgov" not in source

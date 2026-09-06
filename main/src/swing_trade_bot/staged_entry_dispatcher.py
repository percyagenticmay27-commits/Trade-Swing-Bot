"""Paper-only staged entry authorization dispatcher.

This module bridges a resolved manual entry strategy and Swing-authorized capital
into one staged-entry authorization decision. It does not evaluate indicators,
move SGOV/cash, create paper positions, write the execution ledger, or place
broker orders.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .manual_entry_strategy_registry import ManualEntryStrategy
from .staged_entry_reservation import (
    StagedEntryReservation,
    create_reservation,
    record_completed_entry,
)

DispatchAction = Literal["WAIT", "AUTHORIZE_ENTRY", "COMPLETE"]


@dataclass(frozen=True, slots=True)
class StagedEntryDispatchDecision:
    underlying_symbol: str
    execution_symbol: str
    strategy_id: str
    number_of_entries: int
    entry_number: int | None
    authorized_allocation: float
    allocation_per_entry: float
    amount_authorized_this_entry: float
    deployed_allocation_before: float
    reserved_allocation_before: float
    action: DispatchAction
    reason: str
    paper_trade_mode: bool = True
    capital_movement_enabled: bool = False
    paper_position_creation_enabled: bool = False
    paper_ledger_write_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if self.capital_movement_enabled:
            raise ValueError("capital movement is not allowed in dispatcher")
        if self.paper_position_creation_enabled:
            raise ValueError("paper position creation is not allowed in dispatcher")
        if self.paper_ledger_write_enabled:
            raise ValueError("paper ledger writes are not allowed in dispatcher")

    def row(self) -> dict[str, object]:
        return asdict(self)


def dispatch_staged_entry(
    *,
    underlying_symbol: str,
    execution_symbol: str,
    strategy: ManualEntryStrategy,
    total_authorized_allocation: float,
    entry_stage_qualified: bool,
    reservation: StagedEntryReservation | None = None,
) -> tuple[StagedEntryDispatchDecision, StagedEntryReservation]:
    """Return one authorization decision plus unchanged/created reservation state.

    The caller owns indicator evaluation. This dispatcher only decides whether the
    next equal allocation slice may proceed after that stage's entry condition has
    qualified. It never records the entry as completed; completion is acknowledged
    separately after the paper execution layer succeeds.
    """

    underlying = underlying_symbol.strip().upper()
    execution = execution_symbol.strip().upper()
    if not underlying or not execution:
        raise ValueError("underlying_symbol and execution_symbol are required")
    if total_authorized_allocation <= 0:
        raise ValueError("total_authorized_allocation must be positive")

    state = reservation or create_reservation(
        underlying_symbol=underlying,
        execution_symbol=execution,
        strategy_id=strategy.strategy_id,
        total_authorized_allocation=total_authorized_allocation,
        number_of_entries=strategy.number_of_entries,
        entries_completed=0,
    )
    _validate_alignment(
        reservation=state,
        underlying_symbol=underlying,
        execution_symbol=execution,
        strategy=strategy,
        total_authorized_allocation=total_authorized_allocation,
    )

    if state.status == "COMPLETE":
        return (
            _decision(state, action="COMPLETE", entry_number=None, amount=0.0,
                      reason="All configured entry stages are complete"),
            state,
        )
    if state.status == "RELEASED":
        return (
            _decision(state, action="WAIT", entry_number=None, amount=0.0,
                      reason="Reservation was released; a new allocation cycle is required"),
            state,
        )

    next_entry = state.entries_completed + 1
    if not entry_stage_qualified:
        return (
            _decision(
                state,
                action="WAIT",
                entry_number=next_entry,
                amount=0.0,
                reason=f"Entry stage {next_entry} conditions are not satisfied",
            ),
            state,
        )

    amount = _next_slice_amount(state)
    return (
        _decision(
            state,
            action="AUTHORIZE_ENTRY",
            entry_number=next_entry,
            amount=amount,
            reason=f"Entry stage {next_entry} qualified; authorize one reserved allocation slice",
        ),
        state,
    )


def acknowledge_completed_entry(
    reservation: StagedEntryReservation,
) -> StagedEntryReservation:
    """Advance reservation state only after the paper execution layer succeeds."""

    return record_completed_entry(reservation)


def _next_slice_amount(reservation: StagedEntryReservation) -> float:
    remaining_entries = reservation.number_of_entries - reservation.entries_completed
    if remaining_entries <= 0:
        return 0.0
    if remaining_entries == 1:
        return round(reservation.reserved_allocation, 2)
    return min(round(reservation.allocation_per_entry, 2), round(reservation.reserved_allocation, 2))


def _decision(
    reservation: StagedEntryReservation,
    *,
    action: DispatchAction,
    entry_number: int | None,
    amount: float,
    reason: str,
) -> StagedEntryDispatchDecision:
    return StagedEntryDispatchDecision(
        underlying_symbol=reservation.underlying_symbol,
        execution_symbol=reservation.execution_symbol,
        strategy_id=reservation.strategy_id,
        number_of_entries=reservation.number_of_entries,
        entry_number=entry_number,
        authorized_allocation=reservation.total_authorized_allocation,
        allocation_per_entry=reservation.allocation_per_entry,
        amount_authorized_this_entry=round(amount, 2),
        deployed_allocation_before=reservation.deployed_allocation,
        reserved_allocation_before=reservation.reserved_allocation,
        action=action,
        reason=reason,
    )


def _validate_alignment(
    *,
    reservation: StagedEntryReservation,
    underlying_symbol: str,
    execution_symbol: str,
    strategy: ManualEntryStrategy,
    total_authorized_allocation: float,
) -> None:
    if reservation.underlying_symbol != underlying_symbol:
        raise ValueError("reservation underlying does not match dispatch underlying")
    if reservation.execution_symbol != execution_symbol:
        raise ValueError("reservation execution symbol does not match dispatch vehicle")
    if reservation.strategy_id != strategy.strategy_id:
        raise ValueError("reservation strategy does not match resolved manual strategy")
    if reservation.number_of_entries != strategy.number_of_entries:
        raise ValueError("reservation entry count does not match resolved manual strategy")
    if round(reservation.total_authorized_allocation, 2) != round(total_authorized_allocation, 2):
        raise ValueError("reservation allocation does not match current Swing allocation authority")

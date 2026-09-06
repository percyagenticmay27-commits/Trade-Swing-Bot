"""Paper-only staged-entry allocation planning.

The Swing portfolio allocator remains the sole authority for total dollars.
This module only divides that authorized allocation into equal entry slices and
reports deployed versus reserved capital. It does not move SGOV, write a paper
ledger, or create positions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StagedEntryAllocationPlan:
    """Equal-slice deployment plan for one authorized Swing allocation."""

    underlying_symbol: str
    execution_symbol: str
    total_authorized_allocation: float
    number_of_entries: int
    entries_completed: int
    allocation_per_entry: float
    deployed_allocation: float
    reserved_allocation: float
    next_entry_number: int | None
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if self.total_authorized_allocation < 0:
            raise ValueError("total_authorized_allocation cannot be negative")
        if self.number_of_entries < 1:
            raise ValueError("number_of_entries must be at least 1")
        if not 0 <= self.entries_completed <= self.number_of_entries:
            raise ValueError("entries_completed must be between 0 and number_of_entries")


def build_staged_entry_allocation_plan(
    *,
    underlying_symbol: str,
    execution_symbol: str,
    total_authorized_allocation: float,
    number_of_entries: int,
    entries_completed: int = 0,
) -> StagedEntryAllocationPlan:
    """Split Swing-authorized capital evenly across the requested entries.

    Undeployed slices remain reserved for this opportunity until a later
    lifecycle decision deploys or releases them. This function has no account,
    SGOV, broker, or ledger side effects.
    """

    underlying = underlying_symbol.strip().upper()
    execution = execution_symbol.strip().upper()
    if not underlying:
        raise ValueError("underlying_symbol is required")
    if not execution:
        raise ValueError("execution_symbol is required")
    if total_authorized_allocation < 0:
        raise ValueError("total_authorized_allocation cannot be negative")
    if not isinstance(number_of_entries, int) or isinstance(number_of_entries, bool):
        raise ValueError("number_of_entries must be an integer")
    if number_of_entries < 1:
        raise ValueError("number_of_entries must be at least 1")
    if not isinstance(entries_completed, int) or isinstance(entries_completed, bool):
        raise ValueError("entries_completed must be an integer")
    if not 0 <= entries_completed <= number_of_entries:
        raise ValueError("entries_completed must be between 0 and number_of_entries")

    allocation_per_entry = total_authorized_allocation / number_of_entries
    deployed = allocation_per_entry * entries_completed
    reserved = total_authorized_allocation - deployed
    next_entry_number = None if entries_completed == number_of_entries else entries_completed + 1

    return StagedEntryAllocationPlan(
        underlying_symbol=underlying,
        execution_symbol=execution,
        total_authorized_allocation=float(total_authorized_allocation),
        number_of_entries=number_of_entries,
        entries_completed=entries_completed,
        allocation_per_entry=allocation_per_entry,
        deployed_allocation=deployed,
        reserved_allocation=reserved,
        next_entry_number=next_entry_number,
        paper_trade_mode=True,
    )

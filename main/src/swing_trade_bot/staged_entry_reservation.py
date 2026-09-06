"""Paper-only staged-entry capital reservation state.

This module records how much of an already-authorized Swing allocation has been
used versus reserved for later entry stages. It does not move SGOV, create paper
positions, write the execution ledger, or place broker orders.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ReservationStatus = Literal["ACTIVE", "COMPLETE", "RELEASED"]


@dataclass(frozen=True, slots=True)
class StagedEntryReservation:
    underlying_symbol: str
    execution_symbol: str
    strategy_id: str
    total_authorized_allocation: float
    number_of_entries: int
    entries_completed: int
    allocation_per_entry: float
    deployed_allocation: float
    reserved_allocation: float
    status: ReservationStatus
    release_reason: str = ""
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if self.underlying_symbol != self.underlying_symbol.strip().upper():
            raise ValueError("underlying_symbol must be uppercase and trimmed")
        if self.execution_symbol != self.execution_symbol.strip().upper():
            raise ValueError("execution_symbol must be uppercase and trimmed")
        if self.strategy_id != self.strategy_id.strip().upper():
            raise ValueError("strategy_id must be uppercase and trimmed")
        if self.total_authorized_allocation <= 0:
            raise ValueError("total_authorized_allocation must be positive")
        if self.number_of_entries <= 0:
            raise ValueError("number_of_entries must be positive")
        if not 0 <= self.entries_completed <= self.number_of_entries:
            raise ValueError("entries_completed must be within entry count")
        if self.allocation_per_entry <= 0:
            raise ValueError("allocation_per_entry must be positive")
        if self.deployed_allocation < 0 or self.reserved_allocation < 0:
            raise ValueError("deployed/reserved allocation cannot be negative")
        if round(self.deployed_allocation + self.reserved_allocation, 2) > round(self.total_authorized_allocation, 2):
            raise ValueError("deployed plus reserved cannot exceed authorized allocation")
        if self.status == "ACTIVE" and self.reserved_allocation <= 0:
            raise ValueError("ACTIVE reservation requires reserved allocation")
        if self.status in ("COMPLETE", "RELEASED") and self.reserved_allocation != 0:
            raise ValueError(f"{self.status} reservation cannot retain reserved allocation")


def create_reservation(
    *,
    underlying_symbol: str,
    execution_symbol: str,
    strategy_id: str,
    total_authorized_allocation: float,
    number_of_entries: int,
    entries_completed: int = 0,
) -> StagedEntryReservation:
    """Create reservation state from allocator authority and entry count."""

    if total_authorized_allocation <= 0:
        raise ValueError("total_authorized_allocation must be positive")
    if number_of_entries <= 0:
        raise ValueError("number_of_entries must be positive")
    if not 0 <= entries_completed <= number_of_entries:
        raise ValueError("entries_completed must be within entry count")

    per_entry = round(total_authorized_allocation / number_of_entries, 2)
    deployed = round(per_entry * entries_completed, 2)
    if entries_completed >= number_of_entries:
        reserved = 0.0
        status: ReservationStatus = "COMPLETE"
    else:
        reserved = round(total_authorized_allocation - deployed, 2)
        status = "ACTIVE"

    return StagedEntryReservation(
        underlying_symbol=underlying_symbol.strip().upper(),
        execution_symbol=execution_symbol.strip().upper(),
        strategy_id=strategy_id.strip().upper(),
        total_authorized_allocation=round(total_authorized_allocation, 2),
        number_of_entries=number_of_entries,
        entries_completed=entries_completed,
        allocation_per_entry=per_entry,
        deployed_allocation=deployed,
        reserved_allocation=reserved,
        status=status,
    )


def record_completed_entry(reservation: StagedEntryReservation) -> StagedEntryReservation:
    """Advance one staged entry and reduce reserved capital accordingly."""

    if reservation.status != "ACTIVE":
        raise ValueError("only ACTIVE reservations can advance")
    completed = reservation.entries_completed + 1
    return create_reservation(
        underlying_symbol=reservation.underlying_symbol,
        execution_symbol=reservation.execution_symbol,
        strategy_id=reservation.strategy_id,
        total_authorized_allocation=reservation.total_authorized_allocation,
        number_of_entries=reservation.number_of_entries,
        entries_completed=completed,
    )


def release_reservation(
    reservation: StagedEntryReservation,
    *,
    reason: str,
) -> StagedEntryReservation:
    """Release undeployed staged capital back to the normal account pool."""

    if not reason.strip():
        raise ValueError("release reason is required")
    return StagedEntryReservation(
        underlying_symbol=reservation.underlying_symbol,
        execution_symbol=reservation.execution_symbol,
        strategy_id=reservation.strategy_id,
        total_authorized_allocation=reservation.total_authorized_allocation,
        number_of_entries=reservation.number_of_entries,
        entries_completed=reservation.entries_completed,
        allocation_per_entry=reservation.allocation_per_entry,
        deployed_allocation=reservation.deployed_allocation,
        reserved_allocation=0.0,
        status="RELEASED",
        release_reason=reason.strip(),
    )


def write_reservation_state(path: Path, reservations: tuple[StagedEntryReservation, ...]) -> Path:
    """Atomically persist paper reservation evidence."""

    symbols = [item.underlying_symbol for item in reservations if item.status == "ACTIVE"]
    if len(symbols) != len(set(symbols)):
        raise ValueError("only one ACTIVE reservation per underlying is allowed")
    payload = {
        "schema_version": "1.0",
        "paper_trade_mode": True,
        "capital_movement_enabled": False,
        "sgov_movement_enabled": False,
        "paper_position_creation_enabled": False,
        "reservations": [asdict(item) for item in reservations],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path

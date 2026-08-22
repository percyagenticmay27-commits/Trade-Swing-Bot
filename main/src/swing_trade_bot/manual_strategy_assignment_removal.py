"""Authoritative paper-only removal lifecycle for manual strategy assignments.

Swing alone owns registry validation and persistence. Removal is exact and explicit:
callers must name the underlying, strategy, and assignment mode. Strategy definitions
are preserved by default. Optional pruning is allowed only when the definition is no
longer referenced by any assignment and is not the default strategy. Historical
shadow ledgers/performance artifacts are intentionally untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .manual_entry_strategy_form_contract import (
    DEFAULT_OUTPUT_PATH as DEFAULT_FORM_CONTRACT_PATH,
    build_and_write_manual_entry_strategy_form_contract,
)
from .manual_entry_strategy_registry import (
    ManualEntryStrategyRegistry,
    load_manual_entry_strategy_registry,
    write_manual_entry_strategy_registry,
)
from .strategy_assignment_shadow_report import (
    DEFAULT_OUTPUT_PATH as DEFAULT_ASSIGNMENT_REPORT_PATH,
    build_and_write_strategy_assignment_shadow_report,
)

DEFAULT_REGISTRY_PATH = Path("configs/manual_entry_strategies.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
PAPER_POSITION_CREATION_ENABLED = False
HISTORICAL_EVIDENCE_DELETION_ENABLED = False


@dataclass(frozen=True, slots=True)
class ManualStrategyAssignmentRemovalResult:
    status: str
    underlying_symbol: str
    strategy_id: str
    assignment_mode: str
    assignment_removed: bool
    strategy_definition_removed: bool
    registry_path: str
    form_contract_path: str
    assignment_report_path: str
    paper_trade_mode: bool = True


def remove_manual_strategy_assignment(
    *,
    underlying_symbol: str,
    strategy_id: str,
    assignment_mode: str,
    confirm: bool,
    prune_unreferenced_strategy: bool = False,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    form_contract_path: Path = DEFAULT_FORM_CONTRACT_PATH,
    assignment_report_path: Path = DEFAULT_ASSIGNMENT_REPORT_PATH,
) -> ManualStrategyAssignmentRemovalResult:
    """Remove exactly one assignment and optionally prune its orphan definition."""
    if confirm is not True:
        raise ValueError("explicit user confirmation is required for assignment removal")

    underlying = underlying_symbol.strip().upper()
    strategy = strategy_id.strip().upper()
    mode = assignment_mode.strip().upper()
    if not underlying or not strategy:
        raise ValueError("underlying_symbol and strategy_id are required")
    if mode not in {"DIRECT", "SHADOW"}:
        raise ValueError("assignment_mode must be DIRECT or SHADOW")

    registry = load_manual_entry_strategy_registry(registry_path)
    if registry.paper_trade_mode is not True:
        raise ValueError("paper_trade_mode=True is mandatory")

    matches = [
        item
        for item in registry.assignments
        if item.underlying_symbol == underlying
        and item.strategy_id == strategy
        and item.assignment_mode == mode
    ]
    if not matches:
        raise ValueError(f"assignment not found: {underlying} {strategy} {mode}")
    if len(matches) != 1:
        raise ValueError("registry contains duplicate matching assignments")

    remaining_assignments = tuple(
        item
        for item in registry.assignments
        if not (
            item.underlying_symbol == underlying
            and item.strategy_id == strategy
            and item.assignment_mode == mode
        )
    )

    remove_definition = False
    strategies = registry.strategies
    if prune_unreferenced_strategy:
        still_referenced = any(item.strategy_id == strategy for item in remaining_assignments)
        if still_referenced:
            raise ValueError("strategy definition is still referenced by another assignment")
        if registry.default_strategy_id == strategy:
            raise ValueError("default strategy definition cannot be pruned")
        if not any(item.strategy_id == strategy for item in strategies):
            raise ValueError("strategy definition not found")
        strategies = tuple(item for item in strategies if item.strategy_id != strategy)
        remove_definition = True

    updated = ManualEntryStrategyRegistry(
        strategies=strategies,
        assignments=remaining_assignments,
        default_strategy_id=registry.default_strategy_id,
        paper_trade_mode=True,
    )
    write_manual_entry_strategy_registry(registry_path, updated)
    build_and_write_manual_entry_strategy_form_contract(
        registry_path=registry_path,
        output_path=form_contract_path,
    )
    build_and_write_strategy_assignment_shadow_report(
        registry_path=registry_path,
        output_path=assignment_report_path,
    )

    return ManualStrategyAssignmentRemovalResult(
        status="REMOVED",
        underlying_symbol=underlying,
        strategy_id=strategy,
        assignment_mode=mode,
        assignment_removed=True,
        strategy_definition_removed=remove_definition,
        registry_path=str(registry_path),
        form_contract_path=str(form_contract_path),
        assignment_report_path=str(assignment_report_path),
    )

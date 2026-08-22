"""Explicit user-only promotion from SHADOW to DIRECT assignment.

No automatic promotion is permitted. A promoted shadow becomes the one DIRECT
strategy for the underlying. Any previous DIRECT strategy is retained as SHADOW
so its research evidence is preserved and the change remains reversible.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .manual_entry_strategy_form_contract import (
    DEFAULT_OUTPUT_PATH,
    build_and_write_manual_entry_strategy_form_contract,
)
from .manual_entry_strategy_registry import (
    ManualEntryStrategyRegistry,
    UnderlyingEntryAssignment,
    load_manual_entry_strategy_registry,
    write_manual_entry_strategy_registry,
)
from .strategy_assignment_shadow_report import build_and_write_strategy_assignment_shadow_report

DEFAULT_REGISTRY_PATH = Path("configs/manual_entry_strategies.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
AUTO_PROMOTION_ENABLED = False


@dataclass(frozen=True, slots=True)
class ShadowPromotionResult:
    status: str
    underlying_symbol: str
    promoted_strategy_id: str
    previous_direct_strategy_id: str | None
    user_confirmed: bool
    paper_trade_mode: bool = True


def promote_shadow_strategy(
    *,
    underlying_symbol: str,
    strategy_id: str,
    user_confirmed: bool,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    form_contract_path: Path = DEFAULT_OUTPUT_PATH,
) -> ShadowPromotionResult:
    if not user_confirmed:
        raise PermissionError("explicit user confirmation is required for shadow promotion")

    symbol = underlying_symbol.strip().upper()
    target = strategy_id.strip().upper()
    if not symbol or not target:
        raise ValueError("underlying_symbol and strategy_id are required")

    registry = load_manual_entry_strategy_registry(registry_path)
    known = {item.strategy_id for item in registry.strategies}
    if target not in known:
        raise ValueError(f"Unknown strategy_id {target}")

    shadow_match = next(
        (
            item for item in registry.assignments
            if item.underlying_symbol == symbol
            and item.strategy_id == target
            and item.assignment_mode == "SHADOW"
            and item.enabled
        ),
        None,
    )
    if shadow_match is None:
        raise ValueError("strategy must be an enabled SHADOW assignment before promotion")

    previous_direct = next(
        (
            item for item in registry.assignments
            if item.underlying_symbol == symbol
            and item.assignment_mode == "DIRECT"
            and item.enabled
        ),
        None,
    )

    assignments: list[UnderlyingEntryAssignment] = []
    for item in registry.assignments:
        if item.underlying_symbol != symbol:
            assignments.append(item)
            continue
        if item.strategy_id == target and item.assignment_mode == "SHADOW":
            continue
        if item.assignment_mode == "DIRECT":
            # Preserve the previous direct as a shadow challenger.
            if item.strategy_id != target:
                assignments.append(
                    UnderlyingEntryAssignment(
                        underlying_symbol=symbol,
                        strategy_id=item.strategy_id,
                        assignment_mode="SHADOW",
                        enabled=item.enabled,
                        note="Previous DIRECT retained as SHADOW after explicit user promotion.",
                    )
                )
            continue
        assignments.append(item)

    assignments.append(
        UnderlyingEntryAssignment(
            underlying_symbol=symbol,
            strategy_id=target,
            assignment_mode="DIRECT",
            enabled=True,
            note="Promoted from SHADOW by explicit user action.",
        )
    )

    updated = ManualEntryStrategyRegistry(
        strategies=registry.strategies,
        assignments=tuple(assignments),
        default_strategy_id=registry.default_strategy_id,
        paper_trade_mode=True,
    )
    write_manual_entry_strategy_registry(registry_path, updated)
    build_and_write_manual_entry_strategy_form_contract(
        registry_path=registry_path,
        output_path=form_contract_path,
    )
    build_and_write_strategy_assignment_shadow_report(registry_path=registry_path)
    return ShadowPromotionResult(
        status="PROMOTED",
        underlying_symbol=symbol,
        promoted_strategy_id=target,
        previous_direct_strategy_id=(
            None if previous_direct is None else previous_direct.strategy_id
        ),
        user_confirmed=True,
    )

"""Validated SWING-001 intake for user-authored manual entry strategies.

The Enterprise host may submit a form payload to this layer, but only Swing owns
validation and persistence. The handler cannot move capital, write paper trades,
create positions, choose allocation dollars, or override verified execution mapping.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .manual_entry_strategy_form_contract import (
    DEFAULT_OUTPUT_PATH,
    build_and_write_manual_entry_strategy_form_contract,
)
from .manual_entry_strategy_registry import (
    EntryRule,
    ManualEntryStrategy,
    ManualEntryStrategyRegistry,
    UnderlyingEntryAssignment,
    load_manual_entry_strategy_registry,
    write_manual_entry_strategy_registry,
)

DEFAULT_REGISTRY_PATH = Path("configs/manual_entry_strategies.json")
FORBIDDEN_USER_FIELDS = {
    "allocation",
    "allocation_amount",
    "allocated_capital",
    "capital_amount",
    "execution_symbol",
    "execution_vehicle",
    "position_size",
}

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
PAPER_POSITION_CREATION_ENABLED = False


@dataclass(frozen=True, slots=True)
class ManualStrategyIntakeResult:
    status: str
    strategy_id: str
    underlying_symbol: str
    created_strategy: bool
    created_assignment: bool
    registry_path: str
    form_contract_path: str


def _rules(value: object, field: str) -> tuple[EntryRule, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a structured list")
    parsed: list[EntryRule] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ValueError(f"{field}[{index}] must be an object")
        if "left" not in raw or "operator" not in raw or "right" not in raw:
            raise ValueError(f"{field}[{index}] requires left, operator, and right")
        parsed.append(
            EntryRule(
                left=str(raw["left"]),  # type: ignore[arg-type]
                operator=str(raw["operator"]),  # type: ignore[arg-type]
                right=raw["right"],  # type: ignore[arg-type]
                period=None if raw.get("period") in (None, "") else int(raw["period"]),
                label=str(raw.get("label", "")),
            )
        )
    return tuple(parsed)


def _optional_mapping(value: object, field: str) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a structured object")
    return dict(value)


def _validate_submission_authority(submission: Mapping[str, Any]) -> None:
    forbidden = sorted(field for field in FORBIDDEN_USER_FIELDS if field in submission)
    if forbidden:
        raise ValueError(
            "User submission cannot control Swing-owned fields: " + ", ".join(forbidden)
        )
    if submission.get("paper_trade_mode", True) is not True:
        raise ValueError("paper_trade_mode=True is mandatory")
    if submission.get("direction", "LONG").upper() != "LONG":
        raise ValueError("Only LONG manual entry strategies are supported")


def _build_strategy(submission: Mapping[str, Any]) -> ManualEntryStrategy:
    required = ("strategy_id", "name", "underlying_symbol", "timeframe", "rules")
    missing = [field for field in required if submission.get(field) in (None, "", [])]
    if missing:
        raise ValueError("Missing required manual strategy fields: " + ", ".join(missing))
    return ManualEntryStrategy(
        strategy_id=str(submission["strategy_id"]).strip().upper(),
        name=str(submission["name"]).strip(),
        timeframe=str(submission["timeframe"]).strip().upper(),
        rule_logic=str(submission.get("rule_logic", "ALL")).strip().upper(),  # type: ignore[arg-type]
        rules=_rules(submission["rules"], "rules"),
        number_of_entries=int(submission.get("number_of_entries", 1)),
        enabled=bool(submission.get("enabled", True)),
        description=str(submission.get("description", "")),
        direction=str(submission.get("direction", "LONG")).strip().upper(),
        session=str(submission.get("session", "REGULAR_SESSION")).strip(),
        confirmation=_optional_mapping(submission.get("confirmation"), "confirmation"),
        regime_logic=str(submission.get("regime_logic", "ALL")).strip().upper(),  # type: ignore[arg-type]
        regime_filters=_rules(submission.get("regime_filters", []), "regime_filters"),
        exit_policy_id=(
            None
            if submission.get("exit_policy_id") in (None, "")
            else str(submission["exit_policy_id"]).strip()
        ),
        reentry_cooldown=_optional_mapping(
            submission.get("reentry_cooldown"), "reentry_cooldown"
        ),
        paper_trade_mode=True,
    )


def apply_manual_entry_strategy_submission(
    submission: Mapping[str, Any],
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    form_contract_path: Path = DEFAULT_OUTPUT_PATH,
) -> ManualStrategyIntakeResult:
    """Validate and atomically persist one strategy + underlying assignment."""
    _validate_submission_authority(submission)
    strategy = _build_strategy(submission)
    symbol = str(submission["underlying_symbol"]).strip().upper()
    if not symbol or symbol != str(submission["underlying_symbol"]).strip().upper():
        raise ValueError("underlying_symbol is required")

    registry = load_manual_entry_strategy_registry(registry_path)
    strategy_ids = {item.strategy_id for item in registry.strategies}
    assigned_symbols = {item.underlying_symbol for item in registry.assignments}

    strategies = tuple(
        strategy if item.strategy_id == strategy.strategy_id else item
        for item in registry.strategies
    )
    if strategy.strategy_id not in strategy_ids:
        strategies += (strategy,)

    assignment = UnderlyingEntryAssignment(
        underlying_symbol=symbol,
        strategy_id=strategy.strategy_id,
        enabled=bool(submission.get("assignment_enabled", True)),
        note=str(submission.get("assignment_note", "")),
    )
    assignments = tuple(
        assignment if item.underlying_symbol == symbol else item
        for item in registry.assignments
    )
    if symbol not in assigned_symbols:
        assignments += (assignment,)

    updated = ManualEntryStrategyRegistry(
        strategies=strategies,
        assignments=assignments,
        default_strategy_id=registry.default_strategy_id,
        paper_trade_mode=True,
    )
    write_manual_entry_strategy_registry(registry_path, updated)
    build_and_write_manual_entry_strategy_form_contract(
        registry_path=registry_path,
        output_path=form_contract_path,
    )
    return ManualStrategyIntakeResult(
        status="SAVED",
        strategy_id=strategy.strategy_id,
        underlying_symbol=symbol,
        created_strategy=strategy.strategy_id not in strategy_ids,
        created_assignment=symbol not in assigned_symbols,
        registry_path=str(registry_path),
        form_contract_path=str(form_contract_path),
    )

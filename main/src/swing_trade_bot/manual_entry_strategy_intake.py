"""Validated SWING-001 intake for user-authored manual trading strategies.

Only Swing owns validation and persistence. This handler cannot move capital,
write paper trades, create positions, choose allocation dollars, override verified
execution mapping, or place broker orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .manual_entry_strategy_form_contract import DEFAULT_OUTPUT_PATH, build_and_write_manual_entry_strategy_form_contract
from .manual_entry_strategy_registry import (
    SUPPORTED_SOURCES,
    ConditionalExit,
    EntryRule,
    ManualEntryStrategy,
    ManualEntryStrategyRegistry,
    UnderlyingEntryAssignment,
    load_manual_entry_strategy_registry,
    write_manual_entry_strategy_registry,
)
from .strategy_assignment_shadow_report import DEFAULT_OUTPUT_PATH as DEFAULT_ASSIGNMENT_REPORT_PATH, build_and_write_strategy_assignment_shadow_report

DEFAULT_REGISTRY_PATH = Path("configs/manual_entry_strategies.json")
FORBIDDEN_USER_FIELDS = {"allocation", "allocation_amount", "allocated_capital", "capital_amount", "execution_symbol", "execution_vehicle", "position_size"}

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
    assignment_mode: str
    created_strategy: bool
    created_assignment: bool
    registry_path: str
    form_contract_path: str
    assignment_report_path: str


def _canonical_rule_token(value: object) -> str:
    text = str(value).strip()
    lowered = text.lower()
    return lowered if lowered in SUPPORTED_SOURCES else text


def _rule(raw: Mapping[str, Any], field: str) -> EntryRule:
    if "left" not in raw or "operator" not in raw or "right" not in raw:
        raise ValueError(f"{field} requires left, operator, and right")
    right = raw["right"]
    if isinstance(right, str):
        right = _canonical_rule_token(right)
    return EntryRule(
        left=_canonical_rule_token(raw["left"]),  # type: ignore[arg-type]
        operator=str(raw["operator"]).strip(),  # type: ignore[arg-type]
        right=right,  # type: ignore[arg-type]
        period=None if raw.get("period") in (None, "") else int(raw["period"]),
        label=str(raw.get("label", "")),
        factor=None if raw.get("factor") in (None, "") else float(raw["factor"]),
        smoothing=None if raw.get("smoothing") in (None, "") else str(raw["smoothing"]).upper(),
        price_source=None if raw.get("price_source") in (None, "") else str(raw["price_source"]).upper(),
    )


def _rules(value: object, field: str) -> tuple[EntryRule, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a structured list")
    parsed: list[EntryRule] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ValueError(f"{field}[{index}] must be an object")
        parsed.append(_rule(raw, f"{field}[{index}]"))
    return tuple(parsed)


def _optional_mapping(value: object, field: str) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a structured object")
    return dict(value)


def _conditional_exits(value: object) -> tuple[ConditionalExit, ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list):
        raise ValueError("conditional_exits must be a structured list")
    output: list[ConditionalExit] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ValueError(f"conditional_exits[{index}] must be an object")
        condition = raw.get("condition")
        if not isinstance(condition, Mapping):
            raise ValueError(f"conditional_exits[{index}].condition must be an object")
        output.append(
            ConditionalExit(
                condition=_rule(condition, f"conditional_exits[{index}].condition"),
                rule_logic=str(raw.get("rule_logic", "ANY")).upper(),  # type: ignore[arg-type]
                rules=_rules(raw.get("rules", []), f"conditional_exits[{index}].rules"),
                action=str(raw.get("action", "SELL")).upper(),
                label=str(raw.get("label", "")),
                cooldown_bars=int(raw.get("cooldown_bars", 0)),
                cooldown_unit=str(raw.get("cooldown_unit", "TRADING_DAY")).upper(),
                reset_entry_confirmation=bool(raw.get("reset_entry_confirmation", True)),
            )
        )
    return tuple(output)


def _validate_submission_authority(submission: Mapping[str, Any]) -> None:
    forbidden = sorted(field for field in FORBIDDEN_USER_FIELDS if field in submission)
    if forbidden:
        raise ValueError("User submission cannot control Swing-owned fields: " + ", ".join(forbidden))
    if submission.get("paper_trade_mode", True) is not True:
        raise ValueError("paper_trade_mode=True is mandatory")
    if str(submission.get("direction", "LONG")).upper() != "LONG":
        raise ValueError("Only LONG manual entry strategies are supported")
    mode = str(submission.get("assignment_mode", "DIRECT")).strip().upper()
    if mode not in {"DIRECT", "SHADOW"}:
        raise ValueError("assignment_mode must be DIRECT or SHADOW")


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
        confirmation_bars=int(submission.get("confirmation_bars", 1)),
        regime_logic=str(submission.get("regime_logic", "ALL")).strip().upper(),  # type: ignore[arg-type]
        regime_filters=_rules(submission.get("regime_filters", []), "regime_filters"),
        normal_exit_logic=str(submission.get("normal_exit_logic", "ANY")).strip().upper(),  # type: ignore[arg-type]
        normal_exit_rules=_rules(submission.get("normal_exit_rules", []), "normal_exit_rules"),
        conditional_exits=_conditional_exits(submission.get("conditional_exits", [])),
        exit_policy_id=None if submission.get("exit_policy_id") in (None, "") else str(submission["exit_policy_id"]).strip(),
        reentry_cooldown=_optional_mapping(submission.get("reentry_cooldown"), "reentry_cooldown"),
        paper_trade_mode=True,
    )


def apply_manual_entry_strategy_submission(
    submission: Mapping[str, Any],
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    form_contract_path: Path = DEFAULT_OUTPUT_PATH,
    assignment_report_path: Path | None = None,
) -> ManualStrategyIntakeResult:
    """Validate and atomically persist one strategy + DIRECT/SHADOW assignment."""
    _validate_submission_authority(submission)
    strategy = _build_strategy(submission)
    symbol = str(submission["underlying_symbol"]).strip().upper()
    mode = str(submission.get("assignment_mode", "DIRECT")).strip().upper()
    if not symbol:
        raise ValueError("underlying_symbol is required")

    registry = load_manual_entry_strategy_registry(registry_path)
    strategy_ids = {item.strategy_id for item in registry.strategies}
    assignment_key = (symbol, strategy.strategy_id, mode)
    assignment_keys = {(item.underlying_symbol, item.strategy_id, item.assignment_mode) for item in registry.assignments}
    strategies = tuple(strategy if item.strategy_id == strategy.strategy_id else item for item in registry.strategies)
    if strategy.strategy_id not in strategy_ids:
        strategies += (strategy,)

    assignment = UnderlyingEntryAssignment(
        underlying_symbol=symbol,
        strategy_id=strategy.strategy_id,
        assignment_mode=mode,  # type: ignore[arg-type]
        enabled=bool(submission.get("assignment_enabled", True)),
        note=str(submission.get("assignment_note", "")),
    )
    if mode == "DIRECT":
        assignments = tuple(assignment if item.underlying_symbol == symbol and item.assignment_mode == "DIRECT" else item for item in registry.assignments)
        if not any(item.underlying_symbol == symbol and item.assignment_mode == "DIRECT" for item in registry.assignments):
            assignments += (assignment,)
    else:
        assignments = tuple(assignment if item.underlying_symbol == symbol and item.strategy_id == strategy.strategy_id and item.assignment_mode == "SHADOW" else item for item in registry.assignments)
        if assignment_key not in assignment_keys:
            assignments += (assignment,)

    updated = ManualEntryStrategyRegistry(strategies=strategies, assignments=assignments, default_strategy_id=registry.default_strategy_id, paper_trade_mode=True)
    write_manual_entry_strategy_registry(registry_path, updated)
    build_and_write_manual_entry_strategy_form_contract(registry_path=registry_path, output_path=form_contract_path)
    report_path = assignment_report_path or (DEFAULT_ASSIGNMENT_REPORT_PATH if registry_path == DEFAULT_REGISTRY_PATH else form_contract_path.with_name("strategy_assignment_shadow_report.json"))
    build_and_write_strategy_assignment_shadow_report(registry_path=registry_path, output_path=report_path)
    return ManualStrategyIntakeResult(
        status="SAVED",
        strategy_id=strategy.strategy_id,
        underlying_symbol=symbol,
        assignment_mode=mode,
        created_strategy=strategy.strategy_id not in strategy_ids,
        created_assignment=assignment_key not in assignment_keys,
        registry_path=str(registry_path),
        form_contract_path=str(form_contract_path),
        assignment_report_path=str(report_path),
    )

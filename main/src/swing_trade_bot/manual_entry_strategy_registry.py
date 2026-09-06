"""Manual trading-strategy registry and underlying assignment authority.

This module is configuration-only and paper-only. It lets a user define named
strategies and assign one DIRECT strategy plus multiple SHADOW strategies to an
underlying. DIRECT resolution alone may feed future entry authorization; SHADOW
assignments are research-only and cannot create positions, move capital, expose
broker orders, or enable live execution.

The schema can represent entry confirmation, configurable indicator parameters,
normal exit rules, profit-conditional exits, and post-exit cooldown behavior.
Swing retains all dollar-allocation and verified execution-vehicle authority.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

RuleOperator = Literal[">", ">=", "<", "<=", "==", "between"]
RuleSource = Literal[
    "close", "volume", "ema", "sma", "rsi", "volume_average", "market_filter",
    "keltner_middle", "hma", "chop", "position_pl",
]
RuleLogic = Literal["ALL", "ANY"]
AssignmentMode = Literal["DIRECT", "SHADOW"]

SUPPORTED_TIMEFRAMES = {"1D", "4H", "1H", "30M", "15M", "5M"}
SUPPORTED_OPERATORS = {">", ">=", "<", "<=", "==", "between"}
SUPPORTED_SOURCES = {
    "close", "volume", "ema", "sma", "rsi", "volume_average", "market_filter",
    "keltner_middle", "hma", "chop", "position_pl",
}
SUPPORTED_DIRECTIONS = {"LONG"}
SUPPORTED_ASSIGNMENT_MODES = {"DIRECT", "SHADOW"}
SUPPORTED_SMOOTHING = {"WILDER", "EMA", "SMA"}
SUPPORTED_PRICE_SOURCES = {"CLOSE", "OHLC_AVERAGE", "HLC3", "HL2"}


@dataclass(frozen=True, slots=True)
class EntryRule:
    """One declarative comparison used by entry, regime, or exit logic."""

    left: RuleSource
    operator: RuleOperator
    right: float | str | list[float]
    period: int | None = None
    label: str = ""
    factor: float | None = None
    smoothing: str | None = None
    price_source: str | None = None

    def __post_init__(self) -> None:
        if self.left not in SUPPORTED_SOURCES:
            raise ValueError(f"Unsupported rule source: {self.left}")
        if self.operator not in SUPPORTED_OPERATORS:
            raise ValueError(f"Unsupported rule operator: {self.operator}")
        if self.period is not None and self.period <= 0:
            raise ValueError("period must be positive when supplied")
        if self.factor is not None and self.factor <= 0:
            raise ValueError("factor must be positive when supplied")
        if self.smoothing is not None and self.smoothing.upper() not in SUPPORTED_SMOOTHING:
            raise ValueError(f"Unsupported smoothing: {self.smoothing}")
        if self.price_source is not None and self.price_source.upper() not in SUPPORTED_PRICE_SOURCES:
            raise ValueError(f"Unsupported price_source: {self.price_source}")
        if self.operator == "between":
            if not isinstance(self.right, list) or len(self.right) != 2:
                raise ValueError("between requires right=[minimum, maximum]")
            if float(self.right[0]) > float(self.right[1]):
                raise ValueError("between minimum cannot exceed maximum")


@dataclass(frozen=True, slots=True)
class ConditionalExit:
    """Exit branch activated only when its position-state condition is true."""

    condition: EntryRule
    rule_logic: RuleLogic
    rules: tuple[EntryRule, ...]
    action: str = "SELL"
    label: str = ""
    cooldown_bars: int = 0
    cooldown_unit: str = "TRADING_DAY"
    reset_entry_confirmation: bool = True

    def __post_init__(self) -> None:
        if self.condition.left != "position_pl":
            raise ValueError("conditional exit condition must currently use position_pl")
        if self.rule_logic not in ("ALL", "ANY"):
            raise ValueError("conditional exit rule_logic must be ALL or ANY")
        if not self.rules:
            raise ValueError("conditional exit requires at least one exit rule")
        if self.action != "SELL":
            raise ValueError("conditional exit action must be SELL")
        if self.cooldown_bars < 0:
            raise ValueError("cooldown_bars cannot be negative")
        if self.cooldown_unit not in {"TRADING_DAY", "BAR"}:
            raise ValueError("cooldown_unit must be TRADING_DAY or BAR")


@dataclass(frozen=True, slots=True)
class ManualEntryStrategy:
    """User-defined trading strategy; Swing retains capital-allocation authority."""

    strategy_id: str
    name: str
    timeframe: str
    rule_logic: RuleLogic
    rules: tuple[EntryRule, ...]
    number_of_entries: int = 1
    enabled: bool = True
    description: str = ""
    direction: str = "LONG"
    session: str = "REGULAR_SESSION"
    confirmation: dict[str, Any] | None = None
    confirmation_bars: int = 1
    regime_logic: RuleLogic = "ALL"
    regime_filters: tuple[EntryRule, ...] = ()
    normal_exit_logic: RuleLogic = "ANY"
    normal_exit_rules: tuple[EntryRule, ...] = ()
    conditional_exits: tuple[ConditionalExit, ...] = ()
    exit_policy_id: str | None = None
    reentry_cooldown: dict[str, Any] | None = None
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.strategy_id or self.strategy_id != self.strategy_id.strip().upper():
            raise ValueError("strategy_id must be uppercase and trimmed")
        if not self.name.strip():
            raise ValueError("strategy name is required")
        if self.timeframe.upper() not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")
        if self.direction.upper() not in SUPPORTED_DIRECTIONS:
            raise ValueError(f"Unsupported direction: {self.direction}")
        if not self.session.strip():
            raise ValueError("session is required")
        if self.rule_logic not in ("ALL", "ANY"):
            raise ValueError("rule_logic must be ALL or ANY")
        if self.regime_logic not in ("ALL", "ANY"):
            raise ValueError("regime_logic must be ALL or ANY")
        if self.normal_exit_logic not in ("ALL", "ANY"):
            raise ValueError("normal_exit_logic must be ALL or ANY")
        if not self.rules:
            raise ValueError("at least one entry rule is required")
        if not isinstance(self.number_of_entries, int) or isinstance(self.number_of_entries, bool):
            raise ValueError("number_of_entries must be an integer")
        if self.number_of_entries < 1:
            raise ValueError("number_of_entries must be at least 1")
        if not isinstance(self.confirmation_bars, int) or isinstance(self.confirmation_bars, bool):
            raise ValueError("confirmation_bars must be an integer")
        if self.confirmation_bars < 1:
            raise ValueError("confirmation_bars must be at least 1")
        if self.confirmation is not None and not isinstance(self.confirmation, dict):
            raise ValueError("confirmation must be a structured object")
        if self.reentry_cooldown is not None and not isinstance(self.reentry_cooldown, dict):
            raise ValueError("reentry_cooldown must be a structured object")
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")


@dataclass(frozen=True, slots=True)
class UnderlyingEntryAssignment:
    underlying_symbol: str
    strategy_id: str
    assignment_mode: AssignmentMode = "DIRECT"
    enabled: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        if not self.underlying_symbol or self.underlying_symbol != self.underlying_symbol.strip().upper():
            raise ValueError("underlying_symbol must be uppercase and trimmed")
        if not self.strategy_id or self.strategy_id != self.strategy_id.strip().upper():
            raise ValueError("strategy_id must be uppercase and trimmed")
        if self.assignment_mode not in SUPPORTED_ASSIGNMENT_MODES:
            raise ValueError("assignment_mode must be DIRECT or SHADOW")


@dataclass(frozen=True, slots=True)
class ManualEntryStrategyRegistry:
    strategies: tuple[ManualEntryStrategy, ...]
    assignments: tuple[UnderlyingEntryAssignment, ...]
    default_strategy_id: str | None = None
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        strategy_ids = [item.strategy_id for item in self.strategies]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("duplicate strategy_id is not allowed")
        direct_symbols = [item.underlying_symbol for item in self.assignments if item.assignment_mode == "DIRECT"]
        if len(direct_symbols) != len(set(direct_symbols)):
            raise ValueError("an underlying can have only one DIRECT strategy assignment")
        assignment_keys = [(item.underlying_symbol, item.strategy_id, item.assignment_mode) for item in self.assignments]
        if len(assignment_keys) != len(set(assignment_keys)):
            raise ValueError("duplicate strategy assignment is not allowed")
        known = set(strategy_ids)
        for assignment in self.assignments:
            if assignment.strategy_id not in known:
                raise ValueError(f"Unknown strategy_id {assignment.strategy_id} for {assignment.underlying_symbol}")
        if self.default_strategy_id is not None and self.default_strategy_id not in known:
            raise ValueError("default_strategy_id must reference a registered strategy")

    def resolve(self, underlying_symbol: str) -> ManualEntryStrategy | None:
        """Resolve only DIRECT; SHADOW assignments never affect entry authority."""
        symbol = underlying_symbol.strip().upper()
        by_id = {item.strategy_id: item for item in self.strategies}
        for assignment in self.assignments:
            if assignment.underlying_symbol == symbol and assignment.assignment_mode == "DIRECT" and assignment.enabled:
                strategy = by_id[assignment.strategy_id]
                return strategy if strategy.enabled else None
        if self.default_strategy_id is None:
            return None
        strategy = by_id[self.default_strategy_id]
        return strategy if strategy.enabled else None

    def shadow_strategies(self, underlying_symbol: str) -> tuple[ManualEntryStrategy, ...]:
        symbol = underlying_symbol.strip().upper()
        by_id = {item.strategy_id: item for item in self.strategies}
        output: list[ManualEntryStrategy] = []
        for assignment in self.assignments:
            if assignment.underlying_symbol == symbol and assignment.assignment_mode == "SHADOW" and assignment.enabled:
                strategy = by_id[assignment.strategy_id]
                if strategy.enabled:
                    output.append(strategy)
        return tuple(output)


def _parse_rule(rule: dict[str, object]) -> EntryRule:
    return EntryRule(
        left=str(rule["left"]),  # type: ignore[arg-type]
        operator=str(rule["operator"]),  # type: ignore[arg-type]
        right=rule["right"],  # type: ignore[arg-type]
        period=None if rule.get("period") in (None, "") else int(rule["period"]),
        label=str(rule.get("label", "")),
        factor=None if rule.get("factor") in (None, "") else float(rule["factor"]),
        smoothing=None if rule.get("smoothing") in (None, "") else str(rule["smoothing"]).upper(),
        price_source=None if rule.get("price_source") in (None, "") else str(rule["price_source"]).upper(),
    )


def _parse_optional_mapping(value: object, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a structured object")
    return dict(value)


def _parse_conditional_exit(item: dict[str, object]) -> ConditionalExit:
    condition_raw = item.get("condition")
    if not isinstance(condition_raw, dict):
        raise ValueError("conditional exit condition must be an object")
    return ConditionalExit(
        condition=_parse_rule(condition_raw),
        rule_logic=str(item.get("rule_logic", "ANY")),  # type: ignore[arg-type]
        rules=tuple(_parse_rule(rule) for rule in item.get("rules", [])),  # type: ignore[arg-type]
        action=str(item.get("action", "SELL")).upper(),
        label=str(item.get("label", "")),
        cooldown_bars=int(item.get("cooldown_bars", 0)),
        cooldown_unit=str(item.get("cooldown_unit", "TRADING_DAY")).upper(),
        reset_entry_confirmation=bool(item.get("reset_entry_confirmation", True)),
    )


def _parse_strategy(item: dict[str, object]) -> ManualEntryStrategy:
    exit_policy_raw = item.get("exit_policy_id")
    return ManualEntryStrategy(
        strategy_id=str(item["strategy_id"]).strip().upper(),
        name=str(item["name"]),
        timeframe=str(item["timeframe"]).upper(),
        rule_logic=str(item.get("rule_logic", "ALL")),  # type: ignore[arg-type]
        rules=tuple(_parse_rule(rule) for rule in item.get("rules", [])),  # type: ignore[arg-type]
        number_of_entries=int(item.get("number_of_entries", 1)),
        enabled=bool(item.get("enabled", True)),
        description=str(item.get("description", "")),
        direction=str(item.get("direction", "LONG")).upper(),
        session=str(item.get("session", "REGULAR_SESSION")),
        confirmation=_parse_optional_mapping(item.get("confirmation"), "confirmation"),
        confirmation_bars=int(item.get("confirmation_bars", 1)),
        regime_logic=str(item.get("regime_logic", "ALL")),  # type: ignore[arg-type]
        regime_filters=tuple(_parse_rule(rule) for rule in item.get("regime_filters", [])),  # type: ignore[arg-type]
        normal_exit_logic=str(item.get("normal_exit_logic", "ANY")),  # type: ignore[arg-type]
        normal_exit_rules=tuple(_parse_rule(rule) for rule in item.get("normal_exit_rules", [])),  # type: ignore[arg-type]
        conditional_exits=tuple(_parse_conditional_exit(raw) for raw in item.get("conditional_exits", [])),  # type: ignore[arg-type]
        exit_policy_id=None if exit_policy_raw in (None, "") else str(exit_policy_raw),
        reentry_cooldown=_parse_optional_mapping(item.get("reentry_cooldown"), "reentry_cooldown"),
        paper_trade_mode=bool(item.get("paper_trade_mode", True)),
    )


def load_manual_entry_strategy_registry(path: Path) -> ManualEntryStrategyRegistry:
    payload = json.loads(path.read_text(encoding="utf-8"))
    strategies = tuple(_parse_strategy(item) for item in payload.get("strategies", []))
    assignments = tuple(
        UnderlyingEntryAssignment(
            underlying_symbol=str(item["underlying_symbol"]).strip().upper(),
            strategy_id=str(item["strategy_id"]).strip().upper(),
            assignment_mode=str(item.get("assignment_mode", "DIRECT")).strip().upper(),  # type: ignore[arg-type]
            enabled=bool(item.get("enabled", True)),
            note=str(item.get("note", "")),
        )
        for item in payload.get("assignments", [])
    )
    default_strategy_id = payload.get("default_strategy_id")
    if default_strategy_id is not None:
        default_strategy_id = str(default_strategy_id).strip().upper()
    return ManualEntryStrategyRegistry(
        strategies=strategies,
        assignments=assignments,
        default_strategy_id=default_strategy_id,
        paper_trade_mode=bool(payload.get("paper_trade_mode", True)),
    )


def _strategy_to_dict(strategy: ManualEntryStrategy) -> dict[str, object]:
    payload = asdict(strategy)
    payload["rules"] = [asdict(rule) for rule in strategy.rules]
    payload["regime_filters"] = [asdict(rule) for rule in strategy.regime_filters]
    payload["normal_exit_rules"] = [asdict(rule) for rule in strategy.normal_exit_rules]
    payload["conditional_exits"] = [asdict(item) for item in strategy.conditional_exits]
    return payload


def write_manual_entry_strategy_registry(path: Path, registry: ManualEntryStrategyRegistry) -> Path:
    payload = {
        "schema_version": "1.4",
        "paper_trade_mode": True,
        "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR",
        "shadow_allocation_model": "SAME_CURRENT_SWING_ALLOCATION_SIMULATED_ONLY",
        "default_strategy_id": registry.default_strategy_id,
        "strategies": [_strategy_to_dict(strategy) for strategy in registry.strategies],
        "assignments": [asdict(item) for item in registry.assignments],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path

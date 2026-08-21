"""Manual entry-strategy registry and underlying assignment authority.

This module is configuration-only and paper-only. It lets a user define named
entry strategies and explicitly assign them to underlying symbols. It does not
evaluate market data, create paper positions, or place broker orders.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

RuleOperator = Literal[">", ">=", "<", "<=", "==", "between"]
RuleSource = Literal["close", "volume", "ema", "sma", "rsi", "volume_average", "market_filter"]
RuleLogic = Literal["ALL", "ANY"]

SUPPORTED_TIMEFRAMES = {"1D", "4H", "1H", "30M", "15M", "5M"}
SUPPORTED_OPERATORS = {">", ">=", "<", "<=", "==", "between"}
SUPPORTED_SOURCES = {
    "close",
    "volume",
    "ema",
    "sma",
    "rsi",
    "volume_average",
    "market_filter",
}


@dataclass(frozen=True, slots=True)
class EntryRule:
    """One declarative entry condition."""

    left: RuleSource
    operator: RuleOperator
    right: float | str | list[float]
    period: int | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if self.left not in SUPPORTED_SOURCES:
            raise ValueError(f"Unsupported rule source: {self.left}")
        if self.operator not in SUPPORTED_OPERATORS:
            raise ValueError(f"Unsupported rule operator: {self.operator}")
        if self.period is not None and self.period <= 0:
            raise ValueError("period must be positive when supplied")
        if self.operator == "between":
            if not isinstance(self.right, list) or len(self.right) != 2:
                raise ValueError("between requires right=[minimum, maximum]")
            if float(self.right[0]) > float(self.right[1]):
                raise ValueError("between minimum cannot exceed maximum")


@dataclass(frozen=True, slots=True)
class ManualEntryStrategy:
    """A user-defined entry strategy specification.

    ``number_of_entries`` controls only how many equal slices the Swing capital
    allocator may deploy for this strategy. The strategy never owns the dollar
    allocation itself.
    """

    strategy_id: str
    name: str
    timeframe: str
    rule_logic: RuleLogic
    rules: tuple[EntryRule, ...]
    number_of_entries: int = 1
    enabled: bool = True
    description: str = ""
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        normalized_id = self.strategy_id.strip().upper()
        if not normalized_id:
            raise ValueError("strategy_id is required")
        if normalized_id != self.strategy_id:
            raise ValueError("strategy_id must be uppercase and trimmed")
        if not self.name.strip():
            raise ValueError("strategy name is required")
        if self.timeframe.upper() not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")
        if self.rule_logic not in ("ALL", "ANY"):
            raise ValueError("rule_logic must be ALL or ANY")
        if not self.rules:
            raise ValueError("at least one entry rule is required")
        if not isinstance(self.number_of_entries, int) or isinstance(self.number_of_entries, bool):
            raise ValueError("number_of_entries must be an integer")
        if self.number_of_entries < 1:
            raise ValueError("number_of_entries must be at least 1")
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")


@dataclass(frozen=True, slots=True)
class UnderlyingEntryAssignment:
    """Manual assignment of one strategy to one underlying symbol."""

    underlying_symbol: str
    strategy_id: str
    enabled: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        if not self.underlying_symbol.strip():
            raise ValueError("underlying_symbol is required")
        if self.underlying_symbol != self.underlying_symbol.strip().upper():
            raise ValueError("underlying_symbol must be uppercase and trimmed")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id is required")
        if self.strategy_id != self.strategy_id.strip().upper():
            raise ValueError("strategy_id must be uppercase and trimmed")


@dataclass(frozen=True, slots=True)
class ManualEntryStrategyRegistry:
    """Validated manual strategy registry plus underlying assignments."""

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

        assignment_symbols = [item.underlying_symbol for item in self.assignments]
        if len(assignment_symbols) != len(set(assignment_symbols)):
            raise ValueError("an underlying can have only one manual entry strategy assignment")

        known = set(strategy_ids)
        for assignment in self.assignments:
            if assignment.strategy_id not in known:
                raise ValueError(
                    f"Unknown strategy_id {assignment.strategy_id} for {assignment.underlying_symbol}"
                )

        if self.default_strategy_id is not None and self.default_strategy_id not in known:
            raise ValueError("default_strategy_id must reference a registered strategy")

    def resolve(self, underlying_symbol: str) -> ManualEntryStrategy | None:
        """Resolve the active manual strategy for an underlying.

        Explicit enabled assignments take precedence. If none exists, the enabled
        default strategy is returned. Disabled strategies never resolve.
        """

        symbol = underlying_symbol.strip().upper()
        by_id = {item.strategy_id: item for item in self.strategies}

        for assignment in self.assignments:
            if assignment.underlying_symbol == symbol and assignment.enabled:
                strategy = by_id[assignment.strategy_id]
                return strategy if strategy.enabled else None

        if self.default_strategy_id is None:
            return None
        strategy = by_id[self.default_strategy_id]
        return strategy if strategy.enabled else None


def load_manual_entry_strategy_registry(path: Path) -> ManualEntryStrategyRegistry:
    """Load and validate a manual entry strategy registry JSON file."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    strategies = tuple(_parse_strategy(item) for item in payload.get("strategies", []))
    assignments = tuple(
        UnderlyingEntryAssignment(
            underlying_symbol=str(item["underlying_symbol"]).strip().upper(),
            strategy_id=str(item["strategy_id"]).strip().upper(),
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


def write_manual_entry_strategy_registry(
    path: Path,
    registry: ManualEntryStrategyRegistry,
) -> Path:
    """Write a validated registry atomically."""

    payload = {
        "schema_version": "1.1",
        "paper_trade_mode": True,
        "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR",
        "default_strategy_id": registry.default_strategy_id,
        "strategies": [
            {
                **{key: value for key, value in asdict(strategy).items() if key != "rules"},
                "rules": [asdict(rule) for rule in strategy.rules],
            }
            for strategy in registry.strategies
        ],
        "assignments": [asdict(item) for item in registry.assignments],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _parse_strategy(item: dict[str, object]) -> ManualEntryStrategy:
    rules = tuple(
        EntryRule(
            left=str(rule["left"]),  # type: ignore[arg-type]
            operator=str(rule["operator"]),  # type: ignore[arg-type]
            right=rule["right"],  # type: ignore[arg-type]
            period=None if rule.get("period") is None else int(rule["period"]),
            label=str(rule.get("label", "")),
        )
        for rule in item.get("rules", [])  # type: ignore[union-attr]
    )
    return ManualEntryStrategy(
        strategy_id=str(item["strategy_id"]).strip().upper(),
        name=str(item["name"]),
        timeframe=str(item["timeframe"]).upper(),
        rule_logic=str(item.get("rule_logic", "ALL")),  # type: ignore[arg-type]
        rules=rules,
        number_of_entries=int(item.get("number_of_entries", 1)),
        enabled=bool(item.get("enabled", True)),
        description=str(item.get("description", "")),
        paper_trade_mode=bool(item.get("paper_trade_mode", True)),
    )

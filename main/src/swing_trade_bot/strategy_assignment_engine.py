"""Paper-only ticker strategy assignment research module.

This Version 1.3 component compares Strategy A and Strategy B by ticker using
rolling simulated performance windows. It produces assignment recommendations
for research reports only. It does not connect to any brokerage system and it
does not place real orders.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

StrategyName = Literal["Strategy A", "Strategy B"]
STRATEGY_A: StrategyName = "Strategy A"
STRATEGY_B: StrategyName = "Strategy B"

WINDOW_1_WEEK = "1_week"
WINDOW_4_WEEK = "4_week"
WINDOW_8_WEEK = "8_week"
WINDOW_12_WEEK = "12_week"
REQUIRED_WINDOWS = (WINDOW_1_WEEK, WINDOW_4_WEEK, WINDOW_8_WEEK, WINDOW_12_WEEK)

ASSIGNMENT_COLUMNS = (
    "symbol",
    "active_strategy",
    "recommended_strategy",
    "switch_eligible",
    "confidence_level",
    "review_window",
    "cooldown_remaining_weeks",
    "reason",
    "strategy_a_return",
    "strategy_b_return",
    "strategy_a_max_drawdown",
    "strategy_b_max_drawdown",
    "strategy_a_win_rate",
    "strategy_b_win_rate",
    "strategy_a_trade_count",
    "strategy_b_trade_count",
)


@dataclass(frozen=True, slots=True)
class StrategyPerformanceWindow:
    """Performance evidence for one ticker and one review window."""

    symbol: str
    window: str
    strategy: StrategyName
    total_return: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    trade_count: int
    reentry_success_rate: float | None = None

    def __post_init__(self) -> None:
        if self.window not in REQUIRED_WINDOWS:
            raise ValueError(f"Unsupported review window: {self.window}")
        if self.strategy not in (STRATEGY_A, STRATEGY_B):
            raise ValueError(f"Unsupported strategy: {self.strategy}")
        if self.trade_count < 0:
            raise ValueError("trade_count cannot be negative")


@dataclass(frozen=True, slots=True)
class StrategyAssignmentPolicy:
    """Rules for ticker-level strategy assignment research."""

    cooldown_weeks: int = 4
    minimum_return_advantage: float = 2.0
    maximum_drawdown_penalty: float = 3.0
    minimum_trade_count_4_week: int = 3
    minimum_trade_count_8_week: int = 6
    minimum_trade_count_12_week: int = 9
    require_profit_factor_not_worse: bool = True
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if self.cooldown_weeks < 0:
            raise ValueError("cooldown_weeks cannot be negative")


@dataclass(frozen=True, slots=True)
class StrategyAssignment:
    """Ticker-level assignment recommendation."""

    symbol: str
    active_strategy: StrategyName
    recommended_strategy: StrategyName
    switch_eligible: bool
    confidence_level: Literal["warning", "review", "preferred", "high", "hold"]
    review_window: str
    cooldown_remaining_weeks: int
    reason: str
    strategy_a_return: float
    strategy_b_return: float
    strategy_a_max_drawdown: float
    strategy_b_max_drawdown: float
    strategy_a_win_rate: float
    strategy_b_win_rate: float
    strategy_a_trade_count: int
    strategy_b_trade_count: int

    def row(self) -> dict[str, object]:
        return asdict(self)


def assign_strategies(
    performance_windows: Sequence[StrategyPerformanceWindow],
    *,
    active_strategies: Mapping[str, StrategyName] | None = None,
    weeks_since_last_switch: Mapping[str, int] | None = None,
    policy: StrategyAssignmentPolicy | None = None,
) -> list[StrategyAssignment]:
    """Assign Strategy A or Strategy B per ticker.

    One-week evidence is warning-only. Four weeks is the minimum review window,
    eight weeks is preferred, and twelve weeks is high-confidence.
    """

    policy = policy or StrategyAssignmentPolicy()
    active_strategies = {k.upper(): v for k, v in (active_strategies or {}).items()}
    weeks_since_last_switch = {k.upper(): v for k, v in (weeks_since_last_switch or {}).items()}

    by_symbol: dict[str, dict[str, dict[StrategyName, StrategyPerformanceWindow]]] = {}
    for item in performance_windows:
        symbol = item.symbol.upper()
        by_symbol.setdefault(symbol, {}).setdefault(item.window, {})[item.strategy] = item

    assignments: list[StrategyAssignment] = []
    for symbol in sorted(by_symbol):
        active = active_strategies.get(symbol, STRATEGY_A)
        review_window = _select_review_window(by_symbol[symbol])
        pair = by_symbol[symbol].get(review_window, {})
        if STRATEGY_A not in pair or STRATEGY_B not in pair:
            assignments.append(_empty_assignment(symbol, active, review_window, "Missing Strategy A or B evidence"))
            continue

        strategy_a = pair[STRATEGY_A]
        strategy_b = pair[STRATEGY_B]
        cooldown_remaining = max(0, policy.cooldown_weeks - weeks_since_last_switch.get(symbol, policy.cooldown_weeks))
        confidence = _confidence_for_window(review_window)

        if review_window == WINDOW_1_WEEK:
            assignments.append(_assignment(symbol, active, active, False, "warning", review_window, cooldown_remaining, "One-week evidence is early warning only", strategy_a, strategy_b))
            continue
        if cooldown_remaining > 0:
            assignments.append(_assignment(symbol, active, active, False, confidence, review_window, cooldown_remaining, "Strategy assignment cooldown is active", strategy_a, strategy_b))
            continue

        challenger = STRATEGY_B if active == STRATEGY_A else STRATEGY_A
        incumbent_result = strategy_a if active == STRATEGY_A else strategy_b
        challenger_result = strategy_b if challenger == STRATEGY_B else strategy_a
        required_count = _minimum_count(review_window, policy)

        if challenger_result.trade_count < required_count:
            assignments.append(_assignment(symbol, active, active, False, confidence, review_window, cooldown_remaining, "Not enough observations for a reliable strategy change", strategy_a, strategy_b))
            continue

        advantage = challenger_result.total_return - incumbent_result.total_return
        drawdown_penalty = challenger_result.max_drawdown - incumbent_result.max_drawdown
        profit_factor_ok = (not policy.require_profit_factor_not_worse) or challenger_result.profit_factor >= incumbent_result.profit_factor
        switch_eligible = advantage >= policy.minimum_return_advantage and drawdown_penalty <= policy.maximum_drawdown_penalty and profit_factor_ok
        recommended = challenger if switch_eligible else active
        reason = (
            f"{challenger} has stronger paper performance by {advantage:.2f} percentage points with acceptable risk"
            if switch_eligible
            else "Active strategy remains assigned; challenger did not clear return, drawdown, and profit-factor rules"
        )
        assignments.append(_assignment(symbol, active, recommended, switch_eligible, confidence, review_window, cooldown_remaining, reason, strategy_a, strategy_b))
    return assignments


def write_strategy_assignment_outputs(output_dir: Path, assignments: Sequence[StrategyAssignment]) -> tuple[Path, Path, Path]:
    """Write assignment output files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "strategy_assignments.csv"
    json_path = output_dir / "strategy_assignments.json"
    md_path = output_dir / "strategy_assignments.md"

    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=ASSIGNMENT_COLUMNS)
        writer.writeheader()
        writer.writerows(item.row() for item in assignments)

    json_path.write_text(json.dumps({"paper_trade_mode": True, "version": "1.3", "assignments": [item.row() for item in assignments]}, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(format_strategy_assignments_markdown(assignments), encoding="utf-8")
    return csv_path, json_path, md_path


def format_strategy_assignments_markdown(assignments: Sequence[StrategyAssignment]) -> str:
    lines = [
        "# Strategy Assignment Report",
        "",
        "Paper-only strategy assignment output.",
        "",
        "| Symbol | Active | Recommended | Switch | Window | Confidence | Reason |",
        "|---|---|---|---:|---|---|---|",
    ]
    for item in assignments:
        lines.append(f"| {item.symbol} | {item.active_strategy} | {item.recommended_strategy} | {item.switch_eligible} | {item.review_window} | {item.confidence_level} | {item.reason} |")
    lines.append("")
    return "\n".join(lines)


def load_strategy_performance_windows(path: Path) -> list[StrategyPerformanceWindow]:
    records: list[StrategyPerformanceWindow] = []
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        for row in csv.DictReader(input_file):
            records.append(
                StrategyPerformanceWindow(
                    symbol=row["symbol"].upper(),
                    window=row["window"],
                    strategy=_strategy_name(row["strategy"]),
                    total_return=float(row["total_return"]),
                    max_drawdown=float(row["max_drawdown"]),
                    win_rate=float(row["win_rate"]),
                    profit_factor=float(row["profit_factor"]),
                    trade_count=int(row["trade_count"]),
                    reentry_success_rate=None if row.get("reentry_success_rate", "") == "" else float(row["reentry_success_rate"]),
                )
            )
    return records


def _select_review_window(windows: Mapping[str, Mapping[StrategyName, StrategyPerformanceWindow]]) -> str:
    for window in (WINDOW_12_WEEK, WINDOW_8_WEEK, WINDOW_4_WEEK, WINDOW_1_WEEK):
        if window in windows:
            return window
    return WINDOW_1_WEEK


def _confidence_for_window(window: str) -> Literal["warning", "review", "preferred", "high", "hold"]:
    return {WINDOW_12_WEEK: "high", WINDOW_8_WEEK: "preferred", WINDOW_4_WEEK: "review"}.get(window, "warning")


def _minimum_count(window: str, policy: StrategyAssignmentPolicy) -> int:
    if window == WINDOW_12_WEEK:
        return policy.minimum_trade_count_12_week
    if window == WINDOW_8_WEEK:
        return policy.minimum_trade_count_8_week
    if window == WINDOW_4_WEEK:
        return policy.minimum_trade_count_4_week
    return 999_999


def _strategy_name(value: str) -> StrategyName:
    if value in (STRATEGY_A, STRATEGY_B):
        return value  # type: ignore[return-value]
    raise ValueError(f"Unsupported strategy: {value}")


def _empty_assignment(symbol: str, active: StrategyName, review_window: str, reason: str) -> StrategyAssignment:
    empty_a = StrategyPerformanceWindow(symbol, review_window, STRATEGY_A, 0.0, 0.0, 0.0, 0.0, 0)
    empty_b = StrategyPerformanceWindow(symbol, review_window, STRATEGY_B, 0.0, 0.0, 0.0, 0.0, 0)
    return _assignment(symbol, active, active, False, "hold", review_window, 0, reason, empty_a, empty_b)


def _assignment(symbol: str, active: StrategyName, recommended: StrategyName, switch_eligible: bool, confidence: Literal["warning", "review", "preferred", "high", "hold"], review_window: str, cooldown_remaining: int, reason: str, strategy_a: StrategyPerformanceWindow, strategy_b: StrategyPerformanceWindow) -> StrategyAssignment:
    return StrategyAssignment(symbol.upper(), active, recommended, switch_eligible, confidence, review_window, cooldown_remaining, reason, strategy_a.total_return, strategy_b.total_return, strategy_a.max_drawdown, strategy_b.max_drawdown, strategy_a.win_rate, strategy_b.win_rate, strategy_a.trade_count, strategy_b.trade_count)

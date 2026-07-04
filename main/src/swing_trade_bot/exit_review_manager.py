"""Paper-only exit review research manager.

This Version 1.3 module classifies whether a simulated position requires a
research review. It does not place real orders, connect to Robinhood, or connect
to any brokerage system.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

StrategyName = Literal["Strategy A", "Strategy B"]
ReviewOutcome = Literal[
    "continue_holding",
    "monitor_closely",
    "review_required",
    "high_priority_review",
    "thesis_broken_review",
    "strategy_b_reentry_review",
]
ReviewAction = Literal[
    "continue_research",
    "increase_monitoring",
    "perform_exit_review",
    "perform_high_priority_review",
    "perform_thesis_review",
    "perform_reentry_review",
]

STRATEGY_A: StrategyName = "Strategy A"
STRATEGY_B: StrategyName = "Strategy B"


@dataclass(frozen=True, slots=True)
class ExitReviewPolicy:
    """Paper-only thresholds for exit review classification."""

    strategy_b_drawdown_threshold_percent: float = 10.0
    quality_warning_score: float = 70.0
    quality_high_priority_score: float = 55.0
    quality_decline_warning: float = -8.0
    quality_decline_high_priority: float = -15.0
    market_regime_warning_score: float = 45.0
    market_regime_high_priority_score: float = 30.0
    giveback_review_zone: str = "giveback_review_zone"
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if self.strategy_b_drawdown_threshold_percent <= 0:
            raise ValueError("strategy_b_drawdown_threshold_percent must be positive")


@dataclass(frozen=True, slots=True)
class ExitReviewInput:
    """Input evidence for one paper exit review classification."""

    symbol: str
    active_strategy: StrategyName
    lifecycle_state: str
    opportunity_quality_score: float
    opportunity_quality_trend: float
    market_regime_score: float
    thesis_intact: bool
    unrealized_percent: float | None = None
    drawdown_from_high_percent: float | None = None
    profit_protection_zone: str = ""
    reentry_state: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.active_strategy not in (STRATEGY_A, STRATEGY_B):
            raise ValueError(f"Unsupported strategy: {self.active_strategy}")


@dataclass(frozen=True, slots=True)
class ExitReviewResult:
    """Paper-only exit review result."""

    symbol: str
    active_strategy: StrategyName
    outcome: ReviewOutcome
    suggested_review_action: ReviewAction
    lifecycle_state: str
    opportunity_quality_score: float
    opportunity_quality_trend: float
    market_regime_score: float
    thesis_intact: bool
    unrealized_percent: float | None
    drawdown_from_high_percent: float | None
    reason: str

    def row(self) -> dict[str, object]:
        return asdict(self)


def review_exit(
    item: ExitReviewInput,
    *,
    policy: ExitReviewPolicy | None = None,
) -> ExitReviewResult:
    """Classify one simulated position for paper exit review."""

    policy = policy or ExitReviewPolicy()
    symbol = item.symbol.upper()

    if not item.thesis_intact:
        return _result(item, symbol, "thesis_broken_review", "perform_thesis_review", "Thesis evidence is not intact and requires high-confidence review.")

    if item.active_strategy == STRATEGY_B and _drawdown_reached(item.unrealized_percent, policy.strategy_b_drawdown_threshold_percent):
        return _result(item, symbol, "strategy_b_reentry_review", "perform_reentry_review", "Strategy B paper drawdown threshold reached; reentry research review is required.")

    if item.reentry_state in ("reentry_ready", "reentry_setup_improving"):
        return _result(item, symbol, "review_required", "perform_reentry_review", "Ticker is already in a reentry research state.")

    if item.profit_protection_zone == policy.giveback_review_zone:
        return _result(item, symbol, "review_required", "perform_exit_review", "Profit protection evidence indicates a giveback review zone.")

    if _high_priority_quality_or_regime(item, policy):
        return _result(item, symbol, "high_priority_review", "perform_high_priority_review", "Quality, trend, or market regime evidence has weakened significantly.")

    if _warning_quality_or_regime(item, policy):
        return _result(item, symbol, "monitor_closely", "increase_monitoring", "Quality, trend, or market regime evidence has weakened and should be monitored.")

    return _result(item, symbol, "continue_holding", "continue_research", "Paper position remains in normal research status.")


def review_exits(
    items: Sequence[ExitReviewInput],
    *,
    policy: ExitReviewPolicy | None = None,
) -> list[ExitReviewResult]:
    """Review multiple simulated positions."""

    policy = policy or ExitReviewPolicy()
    return [review_exit(item, policy=policy) for item in items]


def write_exit_review_outputs(output_dir: Path, results: Sequence[ExitReviewResult]) -> tuple[Path, Path]:
    """Write JSON and Markdown paper exit review reports."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "exit_review_report.json"
    md_path = output_dir / "exit_review_report.md"
    json_path.write_text(
        json.dumps({"paper_trade_mode": True, "version": "1.3", "reviews": [result.row() for result in results]}, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(format_exit_review_markdown(results), encoding="utf-8")
    return json_path, md_path


def format_exit_review_markdown(results: Sequence[ExitReviewResult]) -> str:
    """Render Markdown exit review report."""

    lines = [
        "# Exit Review Report",
        "",
        "Paper-only research output. No real orders are placed.",
        "",
        "| Symbol | Strategy | Outcome | Suggested Review Action | Quality | Trend | Regime |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result.symbol} | {result.active_strategy} | {result.outcome} | "
            f"{result.suggested_review_action} | {result.opportunity_quality_score:.2f} | "
            f"{result.opportunity_quality_trend:.2f} | {result.market_regime_score:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def _drawdown_reached(unrealized_percent: float | None, threshold: float) -> bool:
    return unrealized_percent is not None and unrealized_percent <= -threshold


def _high_priority_quality_or_regime(item: ExitReviewInput, policy: ExitReviewPolicy) -> bool:
    return (
        item.opportunity_quality_score < policy.quality_high_priority_score
        or item.opportunity_quality_trend <= policy.quality_decline_high_priority
        or item.market_regime_score < policy.market_regime_high_priority_score
    )


def _warning_quality_or_regime(item: ExitReviewInput, policy: ExitReviewPolicy) -> bool:
    return (
        item.opportunity_quality_score < policy.quality_warning_score
        or item.opportunity_quality_trend <= policy.quality_decline_warning
        or item.market_regime_score < policy.market_regime_warning_score
    )


def _result(
    item: ExitReviewInput,
    symbol: str,
    outcome: ReviewOutcome,
    action: ReviewAction,
    reason: str,
) -> ExitReviewResult:
    return ExitReviewResult(
        symbol=symbol,
        active_strategy=item.active_strategy,
        outcome=outcome,
        suggested_review_action=action,
        lifecycle_state=item.lifecycle_state,
        opportunity_quality_score=item.opportunity_quality_score,
        opportunity_quality_trend=item.opportunity_quality_trend,
        market_regime_score=item.market_regime_score,
        thesis_intact=item.thesis_intact,
        unrealized_percent=item.unrealized_percent,
        drawdown_from_high_percent=item.drawdown_from_high_percent,
        reason=reason,
    )

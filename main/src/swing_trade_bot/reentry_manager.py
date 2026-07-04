"""Paper-only reentry research manager.

This Version 1.3 module evaluates whether a ticker in reentry watch has enough
simulated evidence to become reentry-ready. It writes research reports only. It
does not place real orders, connect to Robinhood, or connect to any brokerage
system.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

StrategyName = Literal["Strategy A", "Strategy B"]
ReentryState = Literal[
    "no_reentry_context",
    "reentry_watch",
    "reentry_not_ready",
    "reentry_setup_improving",
    "reentry_ready",
    "reentry_blocked",
]
ReentryAction = Literal[
    "monitor",
    "wait_for_evidence",
    "review_reentry_setup",
    "prepare_reentry_review",
    "block_reentry_review",
]

STRATEGY_A: StrategyName = "Strategy A"
STRATEGY_B: StrategyName = "Strategy B"


@dataclass(frozen=True, slots=True)
class ReentryPolicy:
    """Paper-only thresholds for reentry research."""

    minimum_quality_score: float = 70.0
    minimum_entry_score: float = 70.0
    minimum_market_regime_score: float = 50.0
    maximum_distance_from_reentry_level_percent: float = 3.0
    minimum_wait_days: int = 3
    improving_setup_entry_score: float = 60.0
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if self.maximum_distance_from_reentry_level_percent < 0:
            raise ValueError("maximum_distance_from_reentry_level_percent cannot be negative")
        if self.minimum_wait_days < 0:
            raise ValueError("minimum_wait_days cannot be negative")


@dataclass(frozen=True, slots=True)
class ReentryInput:
    """Input evidence for one ticker reentry review."""

    symbol: str
    active_strategy: StrategyName
    prior_lifecycle_state: str
    opportunity_quality_score: float
    entry_score: float
    market_regime_score: float
    thesis_intact: bool
    distance_from_reentry_level_percent: float | None = None
    days_since_reentry_watch: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        if self.active_strategy not in (STRATEGY_A, STRATEGY_B):
            raise ValueError(f"Unsupported strategy: {self.active_strategy}")
        if self.days_since_reentry_watch < 0:
            raise ValueError("days_since_reentry_watch cannot be negative")


@dataclass(frozen=True, slots=True)
class ReentryReview:
    """Paper-only reentry review output."""

    symbol: str
    active_strategy: StrategyName
    reentry_state: ReentryState
    suggested_review_action: ReentryAction
    opportunity_quality_score: float
    entry_score: float
    market_regime_score: float
    thesis_intact: bool
    distance_from_reentry_level_percent: float | None
    days_since_reentry_watch: int
    reason: str

    def row(self) -> dict[str, object]:
        return asdict(self)


def review_reentry(
    item: ReentryInput,
    *,
    policy: ReentryPolicy | None = None,
) -> ReentryReview:
    """Classify one ticker into a paper reentry state."""

    policy = policy or ReentryPolicy()
    symbol = item.symbol.upper()

    if item.prior_lifecycle_state not in ("reentry_watch", "review_required", "closed_research"):
        return ReentryReview(symbol, item.active_strategy, "no_reentry_context", "monitor", item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, item.distance_from_reentry_level_percent, item.days_since_reentry_watch, "Ticker is not currently in a reentry research context.")

    if not item.thesis_intact:
        return ReentryReview(symbol, item.active_strategy, "reentry_blocked", "block_reentry_review", item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, item.distance_from_reentry_level_percent, item.days_since_reentry_watch, "Reentry review is blocked because thesis evidence is not intact.")

    if item.days_since_reentry_watch < policy.minimum_wait_days:
        return ReentryReview(symbol, item.active_strategy, "reentry_watch", "wait_for_evidence", item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, item.distance_from_reentry_level_percent, item.days_since_reentry_watch, "Minimum paper wait period has not passed.")

    if item.opportunity_quality_score < policy.minimum_quality_score or item.market_regime_score < policy.minimum_market_regime_score:
        return ReentryReview(symbol, item.active_strategy, "reentry_not_ready", "wait_for_evidence", item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, item.distance_from_reentry_level_percent, item.days_since_reentry_watch, "Quality or market regime evidence is not strong enough for reentry review.")

    if item.distance_from_reentry_level_percent is None:
        return ReentryReview(symbol, item.active_strategy, "reentry_setup_improving", "review_reentry_setup", item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, None, item.days_since_reentry_watch, "Reentry level distance is missing; setup requires additional review.")

    if item.entry_score >= policy.minimum_entry_score and item.distance_from_reentry_level_percent <= policy.maximum_distance_from_reentry_level_percent:
        return ReentryReview(symbol, item.active_strategy, "reentry_ready", "prepare_reentry_review", item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, item.distance_from_reentry_level_percent, item.days_since_reentry_watch, "Paper reentry evidence meets quality, entry, regime, timing, and level-distance rules.")

    if item.entry_score >= policy.improving_setup_entry_score:
        return ReentryReview(symbol, item.active_strategy, "reentry_setup_improving", "review_reentry_setup", item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, item.distance_from_reentry_level_percent, item.days_since_reentry_watch, "Paper reentry setup is improving but not ready yet.")

    return ReentryReview(symbol, item.active_strategy, "reentry_not_ready", "wait_for_evidence", item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, item.distance_from_reentry_level_percent, item.days_since_reentry_watch, "Entry evidence is not strong enough for reentry review.")


def review_reentries(
    items: Sequence[ReentryInput],
    *,
    policy: ReentryPolicy | None = None,
) -> list[ReentryReview]:
    """Review multiple ticker reentry records."""

    policy = policy or ReentryPolicy()
    return [review_reentry(item, policy=policy) for item in items]


def write_reentry_outputs(output_dir: Path, reviews: Sequence[ReentryReview]) -> tuple[Path, Path]:
    """Write JSON and Markdown paper reentry reports."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "reentry_report.json"
    md_path = output_dir / "reentry_report.md"
    json_path.write_text(
        json.dumps({"paper_trade_mode": True, "version": "1.3", "reviews": [review.row() for review in reviews]}, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(format_reentry_markdown(reviews), encoding="utf-8")
    return json_path, md_path


def format_reentry_markdown(reviews: Sequence[ReentryReview]) -> str:
    """Render Markdown reentry report."""

    lines = [
        "# Reentry Report",
        "",
        "Paper-only research output. No real orders are placed.",
        "",
        "| Symbol | Strategy | Reentry State | Suggested Review Action | Quality | Entry | Regime |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for review in reviews:
        lines.append(
            f"| {review.symbol} | {review.active_strategy} | {review.reentry_state} | "
            f"{review.suggested_review_action} | {review.opportunity_quality_score:.2f} | "
            f"{review.entry_score:.2f} | {review.market_regime_score:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)

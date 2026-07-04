"""Paper-only trade lifecycle research manager.

This Version 1.3 module classifies the simulated lifecycle state of each ticker.
It writes research reports only. It does not place real orders, connect to
Robinhood, or connect to any brokerage system.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

StrategyName = Literal["Strategy A", "Strategy B"]
LifecycleState = Literal[
    "candidate",
    "watchlist",
    "entry_ready",
    "paper_position",
    "profit_protection",
    "review_required",
    "reentry_watch",
    "closed_research",
]
LifecycleAction = Literal[
    "monitor",
    "prepare_entry_review",
    "continue_research_position",
    "protect_paper_gain",
    "review_thesis",
    "research_reentry",
    "archive_research_case",
]

STRATEGY_A: StrategyName = "Strategy A"
STRATEGY_B: StrategyName = "Strategy B"


@dataclass(frozen=True, slots=True)
class LifecyclePolicy:
    """Configuration for paper lifecycle classification."""

    strategy_b_review_drawdown_percent: float = 10.0
    profit_protection_gain_percent: float = 20.0
    strong_profit_gain_percent: float = 30.0
    minimum_entry_score: float = 70.0
    minimum_quality_score: float = 70.0
    minimum_market_regime_score: float = 50.0
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if self.strategy_b_review_drawdown_percent <= 0:
            raise ValueError("strategy_b_review_drawdown_percent must be positive")


@dataclass(frozen=True, slots=True)
class LifecycleInput:
    """Input evidence for one ticker lifecycle review."""

    symbol: str
    active_strategy: StrategyName
    current_state: LifecycleState
    opportunity_quality_score: float
    entry_score: float
    market_regime_score: float
    thesis_intact: bool
    entry_price: float | None = None
    current_price: float | None = None
    highest_price_since_entry: float | None = None
    days_in_state: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        if self.active_strategy not in (STRATEGY_A, STRATEGY_B):
            raise ValueError(f"Unsupported strategy: {self.active_strategy}")
        if self.days_in_state < 0:
            raise ValueError("days_in_state cannot be negative")


@dataclass(frozen=True, slots=True)
class LifecycleReview:
    """Paper-only lifecycle review output for one ticker."""

    symbol: str
    active_strategy: StrategyName
    prior_state: LifecycleState
    recommended_state: LifecycleState
    suggested_action: LifecycleAction
    unrealized_percent: float | None
    drawdown_from_high_percent: float | None
    quality_score: float
    entry_score: float
    market_regime_score: float
    thesis_intact: bool
    reason: str

    def row(self) -> dict[str, object]:
        return asdict(self)


def review_lifecycle(
    item: LifecycleInput,
    *,
    policy: LifecyclePolicy | None = None,
) -> LifecycleReview:
    """Review one ticker and return its paper lifecycle classification."""

    policy = policy or LifecyclePolicy()
    unrealized = _percent_change(item.entry_price, item.current_price)
    drawdown_from_high = _drawdown_from_high(item.highest_price_since_entry, item.current_price)

    if item.current_state in ("candidate", "watchlist"):
        return _pre_position_review(item, policy, unrealized, drawdown_from_high)

    if item.current_state == "entry_ready":
        return LifecycleReview(
            symbol=item.symbol.upper(),
            active_strategy=item.active_strategy,
            prior_state=item.current_state,
            recommended_state="entry_ready",
            suggested_action="prepare_entry_review",
            unrealized_percent=unrealized,
            drawdown_from_high_percent=drawdown_from_high,
            quality_score=item.opportunity_quality_score,
            entry_score=item.entry_score,
            market_regime_score=item.market_regime_score,
            thesis_intact=item.thesis_intact,
            reason="Entry review conditions remain active for paper research.",
        )

    if item.current_state in ("paper_position", "profit_protection"):
        return _position_review(item, policy, unrealized, drawdown_from_high)

    if item.current_state == "review_required":
        return LifecycleReview(item.symbol.upper(), item.active_strategy, item.current_state, "review_required", "review_thesis", unrealized, drawdown_from_high, item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, "Ticker remains in thesis review status.")

    if item.current_state == "reentry_watch":
        return LifecycleReview(item.symbol.upper(), item.active_strategy, item.current_state, "reentry_watch", "research_reentry", unrealized, drawdown_from_high, item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, "Ticker remains under paper reentry research.")

    return LifecycleReview(item.symbol.upper(), item.active_strategy, item.current_state, "closed_research", "archive_research_case", unrealized, drawdown_from_high, item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, "Research case is closed.")


def review_lifecycles(
    items: Sequence[LifecycleInput],
    *,
    policy: LifecyclePolicy | None = None,
) -> list[LifecycleReview]:
    """Review multiple ticker lifecycle records."""

    policy = policy or LifecyclePolicy()
    return [review_lifecycle(item, policy=policy) for item in items]


def write_trade_lifecycle_outputs(output_dir: Path, reviews: Sequence[LifecycleReview]) -> tuple[Path, Path]:
    """Write JSON and Markdown paper lifecycle reports."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "trade_lifecycle_report.json"
    md_path = output_dir / "trade_lifecycle_report.md"
    json_path.write_text(
        json.dumps({"paper_trade_mode": True, "version": "1.3", "reviews": [review.row() for review in reviews]}, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(format_trade_lifecycle_markdown(reviews), encoding="utf-8")
    return json_path, md_path


def format_trade_lifecycle_markdown(reviews: Sequence[LifecycleReview]) -> str:
    """Render Markdown lifecycle report."""

    lines = [
        "# Trade Lifecycle Report",
        "",
        "Paper-only research output. No real orders are placed.",
        "",
        "| Symbol | Strategy | Prior State | Recommended State | Suggested Review Action | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for review in reviews:
        lines.append(
            f"| {review.symbol} | {review.active_strategy} | {review.prior_state} | "
            f"{review.recommended_state} | {review.suggested_action} | {review.reason} |"
        )
    lines.append("")
    return "\n".join(lines)


def _pre_position_review(
    item: LifecycleInput,
    policy: LifecyclePolicy,
    unrealized: float | None,
    drawdown_from_high: float | None,
) -> LifecycleReview:
    if (
        item.opportunity_quality_score >= policy.minimum_quality_score
        and item.entry_score >= policy.minimum_entry_score
        and item.market_regime_score >= policy.minimum_market_regime_score
        and item.thesis_intact
    ):
        state: LifecycleState = "entry_ready"
        action: LifecycleAction = "prepare_entry_review"
        reason = "Quality, entry, market regime, and thesis checks support entry review."
    else:
        state = "watchlist"
        action = "monitor"
        reason = "Ticker remains in watchlist research until quality, entry, and regime evidence improves."
    return LifecycleReview(item.symbol.upper(), item.active_strategy, item.current_state, state, action, unrealized, drawdown_from_high, item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, reason)


def _position_review(
    item: LifecycleInput,
    policy: LifecyclePolicy,
    unrealized: float | None,
    drawdown_from_high: float | None,
) -> LifecycleReview:
    if not item.thesis_intact or item.opportunity_quality_score < policy.minimum_quality_score:
        return LifecycleReview(item.symbol.upper(), item.active_strategy, item.current_state, "review_required", "review_thesis", unrealized, drawdown_from_high, item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, "Thesis or quality evidence has weakened and requires paper review.")

    if item.active_strategy == STRATEGY_B and unrealized is not None and unrealized <= -policy.strategy_b_review_drawdown_percent:
        return LifecycleReview(item.symbol.upper(), item.active_strategy, item.current_state, "reentry_watch", "research_reentry", unrealized, drawdown_from_high, item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, "Strategy B paper threshold indicates reentry research should be evaluated.")

    if unrealized is not None and unrealized >= policy.profit_protection_gain_percent:
        return LifecycleReview(item.symbol.upper(), item.active_strategy, item.current_state, "profit_protection", "protect_paper_gain", unrealized, drawdown_from_high, item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, "Paper gain has reached the profit-protection review zone.")

    return LifecycleReview(item.symbol.upper(), item.active_strategy, item.current_state, "paper_position", "continue_research_position", unrealized, drawdown_from_high, item.opportunity_quality_score, item.entry_score, item.market_regime_score, item.thesis_intact, "Paper position research remains active; thesis is intact.")


def _percent_change(entry_price: float | None, current_price: float | None) -> float | None:
    if entry_price is None or current_price is None or entry_price == 0:
        return None
    return ((current_price - entry_price) / entry_price) * 100.0


def _drawdown_from_high(highest_price: float | None, current_price: float | None) -> float | None:
    if highest_price is None or current_price is None or highest_price == 0:
        return None
    return ((current_price - highest_price) / highest_price) * 100.0

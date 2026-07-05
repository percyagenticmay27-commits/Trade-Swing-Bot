"""Paper-only thesis monitor.

This Version 1.4 module evaluates whether the original research thesis for a
ticker remains intact. It writes research reports only. It does not place real
orders, connect to Robinhood, or connect to any brokerage system.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

StrategyName = Literal["Strategy A", "Strategy B"]
ThesisState = Literal["strong", "intact", "weakening", "broken", "unknown"]
ThesisAction = Literal[
    "continue_research",
    "monitor_thesis",
    "review_thesis",
    "high_priority_review",
    "insufficient_evidence",
]

STRATEGY_A: StrategyName = "Strategy A"
STRATEGY_B: StrategyName = "Strategy B"


@dataclass(frozen=True, slots=True)
class ThesisMonitorPolicy:
    """Paper-only scoring policy for thesis health."""

    strong_threshold: float = 85.0
    intact_threshold: float = 70.0
    weakening_threshold: float = 55.0
    minimum_required_evidence_count: int = 5
    material_quality_decline: float = -12.0
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if self.minimum_required_evidence_count < 1:
            raise ValueError("minimum_required_evidence_count must be positive")


@dataclass(frozen=True, slots=True)
class ThesisEvidence:
    """Evidence for one ticker thesis review."""

    symbol: str
    active_strategy: StrategyName
    original_thesis: str
    opportunity_quality_score: float | None
    opportunity_quality_trend: float | None
    fundamental_score: float | None
    earnings_score: float | None
    news_sentiment_score: float | None
    conviction_score: float | None
    sector_strength_score: float | None
    market_regime_score: float | None
    technical_health_score: float | None
    analyst_revision_score: float | None = None
    institutional_flow_score: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.active_strategy not in (STRATEGY_A, STRATEGY_B):
            raise ValueError(f"Unsupported strategy: {self.active_strategy}")


@dataclass(frozen=True, slots=True)
class ThesisReview:
    """Paper-only thesis review output."""

    symbol: str
    active_strategy: StrategyName
    thesis_state: ThesisState
    thesis_health_score: float
    thesis_intact: bool
    suggested_review_action: ThesisAction
    evidence_count: int
    weak_evidence_count: int
    original_thesis: str
    reason: str

    def row(self) -> dict[str, object]:
        return asdict(self)


def review_thesis(
    evidence: ThesisEvidence,
    *,
    policy: ThesisMonitorPolicy | None = None,
) -> ThesisReview:
    """Evaluate one ticker thesis."""

    policy = policy or ThesisMonitorPolicy()
    values = _evidence_values(evidence)
    evidence_count = len(values)
    weak_count = sum(1 for value in values if value < policy.weakening_threshold)

    if evidence_count < policy.minimum_required_evidence_count:
        return ThesisReview(
            symbol=evidence.symbol.upper(),
            active_strategy=evidence.active_strategy,
            thesis_state="unknown",
            thesis_health_score=0.0,
            thesis_intact=False,
            suggested_review_action="insufficient_evidence",
            evidence_count=evidence_count,
            weak_evidence_count=weak_count,
            original_thesis=evidence.original_thesis,
            reason="Not enough evidence is available for thesis review.",
        )

    score = _weighted_score(evidence)
    trend = evidence.opportunity_quality_trend if evidence.opportunity_quality_trend is not None else 0.0

    if trend <= policy.material_quality_decline or weak_count >= 3:
        state: ThesisState = "broken" if score < policy.weakening_threshold else "weakening"
    elif score >= policy.strong_threshold:
        state = "strong"
    elif score >= policy.intact_threshold:
        state = "intact"
    elif score >= policy.weakening_threshold:
        state = "weakening"
    else:
        state = "broken"

    action = _action_for_state(state)
    return ThesisReview(
        symbol=evidence.symbol.upper(),
        active_strategy=evidence.active_strategy,
        thesis_state=state,
        thesis_health_score=round(score, 6),
        thesis_intact=state in {"strong", "intact"},
        suggested_review_action=action,
        evidence_count=evidence_count,
        weak_evidence_count=weak_count,
        original_thesis=evidence.original_thesis,
        reason=_reason_for_state(state),
    )


def review_theses(
    items: Sequence[ThesisEvidence],
    *,
    policy: ThesisMonitorPolicy | None = None,
) -> list[ThesisReview]:
    """Review multiple ticker theses."""

    policy = policy or ThesisMonitorPolicy()
    return [review_thesis(item, policy=policy) for item in items]


def write_thesis_monitor_outputs(output_dir: Path, reviews: Sequence[ThesisReview]) -> tuple[Path, Path]:
    """Write JSON and Markdown paper thesis reports."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "thesis_monitor_report.json"
    md_path = output_dir / "thesis_monitor_report.md"
    json_path.write_text(
        json.dumps({"paper_trade_mode": True, "version": "1.4", "reviews": [review.row() for review in reviews]}, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(format_thesis_monitor_markdown(reviews), encoding="utf-8")
    return json_path, md_path


def format_thesis_monitor_markdown(reviews: Sequence[ThesisReview]) -> str:
    """Render Markdown thesis monitor report."""

    lines = [
        "# Thesis Monitor Report",
        "",
        "Paper-only research output. No real orders are placed.",
        "",
        "| Symbol | Strategy | Thesis State | Health Score | Thesis Intact | Suggested Review Action |",
        "|---|---|---|---:|---|---|",
    ]
    for review in reviews:
        lines.append(
            f"| {review.symbol} | {review.active_strategy} | {review.thesis_state} | "
            f"{review.thesis_health_score:.2f} | {review.thesis_intact} | {review.suggested_review_action} |"
        )
    lines.append("")
    return "\n".join(lines)


def _evidence_values(evidence: ThesisEvidence) -> list[float]:
    values = [
        evidence.opportunity_quality_score,
        evidence.fundamental_score,
        evidence.earnings_score,
        evidence.news_sentiment_score,
        evidence.conviction_score,
        evidence.sector_strength_score,
        evidence.market_regime_score,
        evidence.technical_health_score,
        evidence.analyst_revision_score,
        evidence.institutional_flow_score,
    ]
    return [float(value) for value in values if value is not None]


def _weighted_score(evidence: ThesisEvidence) -> float:
    weighted_values: list[tuple[float, float]] = []
    weights = [
        (evidence.opportunity_quality_score, 0.18),
        (evidence.fundamental_score, 0.18),
        (evidence.earnings_score, 0.14),
        (evidence.news_sentiment_score, 0.12),
        (evidence.conviction_score, 0.14),
        (evidence.sector_strength_score, 0.08),
        (evidence.market_regime_score, 0.08),
        (evidence.technical_health_score, 0.04),
        (evidence.analyst_revision_score, 0.02),
        (evidence.institutional_flow_score, 0.02),
    ]
    for value, weight in weights:
        if value is not None:
            weighted_values.append((float(value), weight))
    total_weight = sum(weight for _, weight in weighted_values)
    if total_weight == 0:
        return 0.0
    return sum(value * weight for value, weight in weighted_values) / total_weight


def _action_for_state(state: ThesisState) -> ThesisAction:
    if state == "strong":
        return "continue_research"
    if state == "intact":
        return "monitor_thesis"
    if state == "weakening":
        return "review_thesis"
    if state == "broken":
        return "high_priority_review"
    return "insufficient_evidence"


def _reason_for_state(state: ThesisState) -> str:
    return {
        "strong": "Thesis evidence is strong across core components.",
        "intact": "Thesis evidence remains intact.",
        "weakening": "Thesis evidence is weakening and requires review.",
        "broken": "Thesis evidence has materially deteriorated.",
        "unknown": "Not enough evidence is available for thesis review.",
    }[state]

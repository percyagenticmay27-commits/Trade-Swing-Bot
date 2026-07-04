"""Paper-only profit protection research manager.

This Version 1.3 module classifies simulated gain and giveback zones. It writes
research reports only. It does not place real orders, connect to Robinhood, or
connect to any brokerage system.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

StrategyName = Literal["Strategy A", "Strategy B"]
ProtectionZone = Literal[
    "no_position_data",
    "below_protection_zone",
    "standard_protection_zone",
    "strong_trend_zone",
    "giveback_review_zone",
]
ProtectionAction = Literal[
    "monitor",
    "standard_profit_review",
    "strong_trend_review",
    "giveback_review",
    "missing_data_review",
]

STRATEGY_A: StrategyName = "Strategy A"
STRATEGY_B: StrategyName = "Strategy B"


@dataclass(frozen=True, slots=True)
class ProfitProtectionPolicy:
    """Paper-only thresholds for profit protection research."""

    standard_gain_percent: float = 20.0
    strong_gain_percent: float = 30.0
    standard_giveback_percent: float = 5.0
    strong_giveback_percent: float = 10.0
    paper_trade_mode: bool = True

    def __post_init__(self) -> None:
        if not self.paper_trade_mode:
            raise ValueError("paper_trade_mode=True is mandatory")
        if self.standard_gain_percent <= 0 or self.strong_gain_percent <= 0:
            raise ValueError("gain thresholds must be positive")
        if self.strong_gain_percent < self.standard_gain_percent:
            raise ValueError("strong_gain_percent must be >= standard_gain_percent")
        if self.standard_giveback_percent <= 0 or self.strong_giveback_percent <= 0:
            raise ValueError("giveback thresholds must be positive")


@dataclass(frozen=True, slots=True)
class ProfitProtectionInput:
    """Input evidence for one paper profit protection review."""

    symbol: str
    active_strategy: StrategyName
    entry_price: float | None
    current_price: float | None
    highest_price_since_entry: float | None
    thesis_intact: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        if self.active_strategy not in (STRATEGY_A, STRATEGY_B):
            raise ValueError(f"Unsupported strategy: {self.active_strategy}")


@dataclass(frozen=True, slots=True)
class ProfitProtectionReview:
    """Paper-only profit protection classification."""

    symbol: str
    active_strategy: StrategyName
    protection_zone: ProtectionZone
    suggested_review_action: ProtectionAction
    unrealized_percent: float | None
    drawdown_from_high_percent: float | None
    thesis_intact: bool
    reason: str

    def row(self) -> dict[str, object]:
        return asdict(self)


def review_profit_protection(
    item: ProfitProtectionInput,
    *,
    policy: ProfitProtectionPolicy | None = None,
) -> ProfitProtectionReview:
    """Classify one ticker into a paper profit protection zone."""

    policy = policy or ProfitProtectionPolicy()
    unrealized = _percent_change(item.entry_price, item.current_price)
    drawdown = _drawdown_from_high(item.highest_price_since_entry, item.current_price)

    if unrealized is None or drawdown is None:
        return ProfitProtectionReview(
            item.symbol.upper(),
            item.active_strategy,
            "no_position_data",
            "missing_data_review",
            unrealized,
            drawdown,
            item.thesis_intact,
            "Position price data is incomplete for paper profit protection review.",
        )

    giveback = abs(drawdown) if drawdown < 0 else 0.0

    if unrealized >= policy.strong_gain_percent:
        if giveback >= policy.strong_giveback_percent:
            return ProfitProtectionReview(item.symbol.upper(), item.active_strategy, "giveback_review_zone", "giveback_review", unrealized, drawdown, item.thesis_intact, "Strong gain zone has experienced a large paper giveback and needs review.")
        return ProfitProtectionReview(item.symbol.upper(), item.active_strategy, "strong_trend_zone", "strong_trend_review", unrealized, drawdown, item.thesis_intact, "Paper gain is in the strong trend review zone.")

    if unrealized >= policy.standard_gain_percent:
        if giveback >= policy.standard_giveback_percent:
            return ProfitProtectionReview(item.symbol.upper(), item.active_strategy, "giveback_review_zone", "giveback_review", unrealized, drawdown, item.thesis_intact, "Standard gain zone has experienced a paper giveback and needs review.")
        return ProfitProtectionReview(item.symbol.upper(), item.active_strategy, "standard_protection_zone", "standard_profit_review", unrealized, drawdown, item.thesis_intact, "Paper gain is in the standard profit protection review zone.")

    return ProfitProtectionReview(item.symbol.upper(), item.active_strategy, "below_protection_zone", "monitor", unrealized, drawdown, item.thesis_intact, "Paper gain has not reached the protection review zone.")


def review_profit_protections(
    items: Sequence[ProfitProtectionInput],
    *,
    policy: ProfitProtectionPolicy | None = None,
) -> list[ProfitProtectionReview]:
    """Review multiple paper positions."""

    policy = policy or ProfitProtectionPolicy()
    return [review_profit_protection(item, policy=policy) for item in items]


def write_profit_protection_outputs(output_dir: Path, reviews: Sequence[ProfitProtectionReview]) -> tuple[Path, Path]:
    """Write JSON and Markdown paper profit protection reports."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "profit_protection_report.json"
    md_path = output_dir / "profit_protection_report.md"
    json_path.write_text(
        json.dumps({"paper_trade_mode": True, "version": "1.3", "reviews": [review.row() for review in reviews]}, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(format_profit_protection_markdown(reviews), encoding="utf-8")
    return json_path, md_path


def format_profit_protection_markdown(reviews: Sequence[ProfitProtectionReview]) -> str:
    """Render Markdown profit protection report."""

    lines = [
        "# Profit Protection Report",
        "",
        "Paper-only research output. No real orders are placed.",
        "",
        "| Symbol | Strategy | Zone | Suggested Review Action | Unrealized % | Drawdown From High % |",
        "|---|---|---|---|---:|---:|",
    ]
    for review in reviews:
        unrealized = "" if review.unrealized_percent is None else f"{review.unrealized_percent:.2f}"
        drawdown = "" if review.drawdown_from_high_percent is None else f"{review.drawdown_from_high_percent:.2f}"
        lines.append(
            f"| {review.symbol} | {review.active_strategy} | {review.protection_zone} | "
            f"{review.suggested_review_action} | {unrealized} | {drawdown} |"
        )
    lines.append("")
    return "\n".join(lines)


def _percent_change(entry_price: float | None, current_price: float | None) -> float | None:
    if entry_price is None or current_price is None or entry_price == 0:
        return None
    return ((current_price - entry_price) / entry_price) * 100.0


def _drawdown_from_high(highest_price: float | None, current_price: float | None) -> float | None:
    if highest_price is None or current_price is None or highest_price == 0:
        return None
    return ((current_price - highest_price) / highest_price) * 100.0

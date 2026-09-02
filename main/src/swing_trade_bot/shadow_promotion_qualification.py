"""Promotion qualification for one Primary and up to three SWING-001 Shadows.

This module generalizes the frozen Strategy Lab promotion gates without changing
them. Each Shadow is reviewed independently against the current Primary. A Shadow
must outperform for three consecutive reviews, have at least 20 trades, have a
profit factor no worse than the Primary, and keep maximum drawdown within the
existing +5 tolerance. If multiple Shadows qualify in the same review, one winner
is selected deterministically by return, profit factor, lower drawdown, trade
count, then Shadow order.

Qualification never mutates strategy assignments. The winning qualified Shadow is
queued into the pending-veto lifecycle; promotion can occur only after the supplied
veto deadline expires without an active user veto.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .shadow_promotion_lifecycle import DEFAULT_LIFECYCLE_PATH, PromotionLifecycleEvent, queue_qualified_shadow

DEFAULT_REVIEW_HISTORY_PATH = Path("results/shadow_promotion_review_history.json")

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False

REQUIRED_CONSECUTIVE_REVIEWS = 3
MINIMUM_TRADE_COUNT = 20
DRAWDOWN_TOLERANCE = 5.0
MAX_ACTIVE_SHADOWS = 3


@dataclass(frozen=True, slots=True)
class PromotionPerformance:
    strategy_id: str
    total_return: float
    profit_factor: float
    max_drawdown: float
    trade_count: int
    shadow_order: int = 0

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id is required")
        if self.trade_count < 0:
            raise ValueError("trade_count cannot be negative")
        if self.shadow_order < 0:
            raise ValueError("shadow_order cannot be negative")


@dataclass(frozen=True, slots=True)
class ShadowQualificationReview:
    underlying_symbol: str
    strategy_id: str
    months_outperforming_primary: int
    return_gate: bool
    consecutive_reviews_gate: bool
    trade_count_gate: bool
    profit_factor_gate: bool
    drawdown_gate: bool
    qualified: bool
    total_return: float
    profit_factor: float
    max_drawdown: float
    trade_count: int
    shadow_order: int


@dataclass(frozen=True, slots=True)
class QualificationResult:
    underlying_symbol: str
    primary_strategy_id: str
    reviews: tuple[ShadowQualificationReview, ...]
    qualified_strategy_id: str | None
    paper_trade_mode: bool = True


def _history_key(symbol: str, strategy_id: str) -> str:
    return f"{symbol.upper()}::{strategy_id.upper()}"


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def load_review_history(path: str | Path = DEFAULT_REVIEW_HISTORY_PATH) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        return {
            "schema_version": "1.0",
            "strategy_id": "SWING-001",
            "paper_trade_mode": True,
            "required_consecutive_reviews": REQUIRED_CONSECUTIVE_REVIEWS,
            "minimum_trade_count": MINIMUM_TRADE_COUNT,
            "drawdown_tolerance": DRAWDOWN_TOLERANCE,
            "counters": {},
        }
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("shadow promotion review history root must be an object")
    if payload.get("strategy_id") != "SWING-001":
        raise ValueError("shadow promotion review history strategy_id must be SWING-001")
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("shadow promotion review history paper_trade_mode must be true")
    counters = payload.get("counters")
    if not isinstance(counters, dict):
        raise ValueError("shadow promotion review history counters must be an object")
    return payload


def evaluate_shadow_qualification(
    *,
    underlying_symbol: str,
    primary: PromotionPerformance,
    shadows: Sequence[PromotionPerformance],
    prior_counters: Mapping[str, int] | None = None,
    drawdown_tolerance: float = DRAWDOWN_TOLERANCE,
) -> QualificationResult:
    """Apply the frozen five Strategy Lab gates independently to each Shadow."""
    symbol = underlying_symbol.strip().upper()
    if not symbol:
        raise ValueError("underlying_symbol is required")
    if len(shadows) > MAX_ACTIVE_SHADOWS:
        raise ValueError("at most three active Shadows may be reviewed")
    if drawdown_tolerance != DRAWDOWN_TOLERANCE:
        raise ValueError("Version 1 promotion drawdown tolerance is frozen at 5.0")

    counters = prior_counters or {}
    reviews: list[ShadowQualificationReview] = []
    for shadow in shadows:
        return_gate = shadow.total_return > primary.total_return
        prior = int(counters.get(_history_key(symbol, shadow.strategy_id), 0))
        months = prior + 1 if return_gate else 0
        consecutive_gate = months >= REQUIRED_CONSECUTIVE_REVIEWS
        trade_gate = shadow.trade_count >= MINIMUM_TRADE_COUNT
        pf_gate = shadow.profit_factor >= primary.profit_factor
        dd_gate = shadow.max_drawdown <= primary.max_drawdown + drawdown_tolerance
        qualified = return_gate and consecutive_gate and trade_gate and pf_gate and dd_gate
        reviews.append(
            ShadowQualificationReview(
                underlying_symbol=symbol,
                strategy_id=shadow.strategy_id.upper(),
                months_outperforming_primary=months,
                return_gate=return_gate,
                consecutive_reviews_gate=consecutive_gate,
                trade_count_gate=trade_gate,
                profit_factor_gate=pf_gate,
                drawdown_gate=dd_gate,
                qualified=qualified,
                total_return=shadow.total_return,
                profit_factor=shadow.profit_factor,
                max_drawdown=shadow.max_drawdown,
                trade_count=shadow.trade_count,
                shadow_order=shadow.shadow_order,
            )
        )

    eligible = [row for row in reviews if row.qualified]
    winner = None
    if eligible:
        winner = sorted(
            eligible,
            key=lambda row: (
                -row.total_return,
                -row.profit_factor,
                row.max_drawdown,
                -row.trade_count,
                row.shadow_order,
                row.strategy_id,
            ),
        )[0].strategy_id

    return QualificationResult(
        underlying_symbol=symbol,
        primary_strategy_id=primary.strategy_id.upper(),
        reviews=tuple(reviews),
        qualified_strategy_id=winner,
    )


def review_and_queue_qualified_shadow(
    *,
    underlying_symbol: str,
    primary: PromotionPerformance,
    shadows: Sequence[PromotionPerformance],
    qualified_at: str,
    veto_deadline: str,
    review_history_path: str | Path = DEFAULT_REVIEW_HISTORY_PATH,
    lifecycle_path: str | Path = DEFAULT_LIFECYCLE_PATH,
) -> tuple[QualificationResult, PromotionLifecycleEvent | None]:
    """Persist independent counters and queue the single deterministic winner."""
    history_path = Path(review_history_path)
    history = load_review_history(history_path)
    raw_counters = history["counters"]
    counters = {str(key): int(value) for key, value in raw_counters.items()}
    result = evaluate_shadow_qualification(
        underlying_symbol=underlying_symbol,
        primary=primary,
        shadows=shadows,
        prior_counters=counters,
    )

    for review in result.reviews:
        counters[_history_key(result.underlying_symbol, review.strategy_id)] = review.months_outperforming_primary
    updated = dict(history)
    updated["counters"] = counters
    updated["last_review"] = {
        "underlying_symbol": result.underlying_symbol,
        "primary_strategy_id": result.primary_strategy_id,
        "qualified_strategy_id": result.qualified_strategy_id,
        "reviews": [asdict(row) for row in result.reviews],
    }
    _atomic_json(history_path, updated)

    queued = None
    if result.qualified_strategy_id is not None:
        winning_review = next(row for row in result.reviews if row.strategy_id == result.qualified_strategy_id)
        queued = queue_qualified_shadow(
            underlying_symbol=result.underlying_symbol,
            strategy_id=result.qualified_strategy_id,
            qualified_at=qualified_at,
            veto_deadline=veto_deadline,
            lifecycle_path=lifecycle_path,
            qualification_evidence={
                "primary_strategy_id": result.primary_strategy_id,
                "total_return": winning_review.total_return,
                "primary_total_return": primary.total_return,
                "months_outperforming_primary": winning_review.months_outperforming_primary,
                "trade_count": winning_review.trade_count,
                "profit_factor": winning_review.profit_factor,
                "primary_profit_factor": primary.profit_factor,
                "max_drawdown": winning_review.max_drawdown,
                "primary_max_drawdown": primary.max_drawdown,
                "drawdown_tolerance": DRAWDOWN_TOLERANCE,
                "all_five_gates_passed": True,
            },
        )
    return result, queued

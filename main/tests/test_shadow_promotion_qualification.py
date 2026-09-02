from __future__ import annotations

from swing_trade_bot.shadow_promotion_qualification import (
    PromotionPerformance,
    evaluate_shadow_qualification,
    load_review_history,
    review_and_queue_qualified_shadow,
)
from swing_trade_bot.shadow_promotion_lifecycle import PENDING_VETO, load_promotion_lifecycle


def _primary() -> PromotionPerformance:
    return PromotionPerformance("PRIMARY_A", total_return=10.0, profit_factor=1.5, max_drawdown=8.0, trade_count=30)


def test_each_shadow_keeps_independent_consecutive_review_counter() -> None:
    result = evaluate_shadow_qualification(
        underlying_symbol="SOXL",
        primary=_primary(),
        shadows=(
            PromotionPerformance("S1", 12.0, 1.6, 9.0, 25, shadow_order=1),
            PromotionPerformance("S2", 9.0, 1.8, 7.0, 30, shadow_order=2),
        ),
        prior_counters={"SOXL::S1": 2, "SOXL::S2": 2},
    )
    by_id = {row.strategy_id: row for row in result.reviews}
    assert by_id["S1"].months_outperforming_primary == 3
    assert by_id["S1"].qualified is True
    assert by_id["S2"].months_outperforming_primary == 0
    assert by_id["S2"].qualified is False
    assert result.qualified_strategy_id == "S1"


def test_all_five_frozen_gates_are_required() -> None:
    primary = _primary()
    shadows = (
        PromotionPerformance("RETURN_FAIL", 10.0, 2.0, 5.0, 30, 1),
        PromotionPerformance("MONTH_FAIL", 12.0, 2.0, 5.0, 30, 2),
        PromotionPerformance("TRADES_FAIL", 12.0, 2.0, 5.0, 19, 3),
    )
    result = evaluate_shadow_qualification(
        underlying_symbol="SOXL",
        primary=primary,
        shadows=shadows,
        prior_counters={"SOXL::RETURN_FAIL": 2, "SOXL::MONTH_FAIL": 1, "SOXL::TRADES_FAIL": 2},
    )
    assert result.qualified_strategy_id is None

    pf = evaluate_shadow_qualification(
        underlying_symbol="SOXL",
        primary=primary,
        shadows=(PromotionPerformance("PF_FAIL", 12.0, 1.49, 5.0, 30, 1),),
        prior_counters={"SOXL::PF_FAIL": 2},
    )
    assert pf.qualified_strategy_id is None

    dd = evaluate_shadow_qualification(
        underlying_symbol="SOXL",
        primary=primary,
        shadows=(PromotionPerformance("DD_FAIL", 12.0, 2.0, 13.01, 30, 1),),
        prior_counters={"SOXL::DD_FAIL": 2},
    )
    assert dd.qualified_strategy_id is None


def test_drawdown_boundary_preserves_existing_plus_five_tolerance() -> None:
    result = evaluate_shadow_qualification(
        underlying_symbol="SOXL",
        primary=_primary(),
        shadows=(PromotionPerformance("S1", 12.0, 1.5, 13.0, 20, 1),),
        prior_counters={"SOXL::S1": 2},
    )
    assert result.reviews[0].drawdown_gate is True
    assert result.qualified_strategy_id == "S1"


def test_multiple_eligible_shadows_use_deterministic_tie_break() -> None:
    result = evaluate_shadow_qualification(
        underlying_symbol="SOXL",
        primary=_primary(),
        shadows=(
            PromotionPerformance("S1", 15.0, 1.8, 10.0, 25, 1),
            PromotionPerformance("S2", 15.0, 1.9, 11.0, 25, 2),
            PromotionPerformance("S3", 14.0, 3.0, 2.0, 100, 3),
        ),
        prior_counters={"SOXL::S1": 2, "SOXL::S2": 2, "SOXL::S3": 2},
    )
    assert result.qualified_strategy_id == "S2"


def test_review_history_persists_by_symbol_and_strategy_and_winner_enters_pending_veto(tmp_path) -> None:
    history_path = tmp_path / "review_history.json"
    lifecycle_path = tmp_path / "lifecycle.json"

    for month in range(1, 4):
        result, queued = review_and_queue_qualified_shadow(
            underlying_symbol="SOXL",
            primary=_primary(),
            shadows=(PromotionPerformance("S1", 12.0, 1.6, 9.0, 25, 1),),
            qualified_at=f"2026-0{month}-01T12:00:00Z",
            veto_deadline=f"2026-0{month}-02T12:00:00Z",
            review_history_path=history_path,
            lifecycle_path=lifecycle_path,
        )
        if month < 3:
            assert result.qualified_strategy_id is None
            assert queued is None
        else:
            assert result.qualified_strategy_id == "S1"
            assert queued is not None
            assert queued.status == PENDING_VETO

    history = load_review_history(history_path)
    assert history["counters"]["SOXL::S1"] == 3
    lifecycle = load_promotion_lifecycle(lifecycle_path)
    assert len(lifecycle["events"]) == 1
    assert lifecycle["events"][0]["qualification_evidence"]["all_five_gates_passed"] is True


def test_more_than_three_active_shadows_is_rejected() -> None:
    shadows = tuple(PromotionPerformance(f"S{n}", 12.0, 1.6, 9.0, 25, n) for n in range(1, 5))
    try:
        evaluate_shadow_qualification(underlying_symbol="SOXL", primary=_primary(), shadows=shadows)
    except ValueError as exc:
        assert "at most three" in str(exc)
    else:
        raise AssertionError("expected more-than-three Shadow guard")

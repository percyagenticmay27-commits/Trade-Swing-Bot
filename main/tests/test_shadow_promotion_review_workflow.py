from __future__ import annotations

import math
from types import SimpleNamespace

import swing_trade_bot.shadow_promotion_review_workflow as workflow
from swing_trade_bot.shadow_promotion_qualification import PromotionPerformance


def test_canonical_performance_converts_common_allocation_dollars_to_percentages() -> None:
    result = workflow._canonical_performance(
        "SHADOW_A",
        200.0,
        {
            "net_pl": 20.0,
            "max_drawdown": -10.0,
            "gross_profit": 30.0,
            "gross_loss": -10.0,
            "profit_factor": 3.0,
            "trade_count": 25,
        },
        shadow_order=2,
    )
    assert result.total_return == 10.0
    assert result.max_drawdown == 5.0
    assert result.profit_factor == 3.0
    assert result.trade_count == 25
    assert result.shadow_order == 2


def test_no_loss_profit_factor_matches_strategy_lab_infinity_semantics() -> None:
    result = workflow._canonical_performance(
        "SHADOW_A",
        100.0,
        {
            "net_pl": 15.0,
            "max_drawdown": 0.0,
            "gross_profit": 15.0,
            "gross_loss": 0.0,
            "profit_factor": None,
            "trade_count": 20,
        },
    )
    assert math.isinf(result.profit_factor)


def _registry() -> SimpleNamespace:
    primary = SimpleNamespace(strategy_id="PRIMARY_A", enabled=True)
    shadow = SimpleNamespace(strategy_id="SHADOW_A", enabled=True)
    return SimpleNamespace(
        strategies=(primary, shadow),
        assignments=(
            SimpleNamespace(underlying_symbol="SOXL", strategy_id="PRIMARY_A", assignment_mode="DIRECT", enabled=True),
            SimpleNamespace(underlying_symbol="SOXL", strategy_id="SHADOW_A", assignment_mode="SHADOW", enabled=True),
        ),
    )


def _patch_evidence(monkeypatch, *, shadow_quantity: float = 12.5) -> None:
    monkeypatch.setattr(workflow, "load_manual_entry_strategy_registry", lambda path: _registry())
    monkeypatch.setattr(workflow, "_mapping", lambda path: {"SOXL": "SOXL"})
    monkeypatch.setattr(workflow, "_load_json", lambda path: {"allocations": []})
    monkeypatch.setattr(workflow, "_allocation", lambda payload, underlying, vehicle: 100.0)
    monkeypatch.setattr(workflow, "_primary_share_quantity", lambda path, vehicle: 12.5)
    monkeypatch.setattr(
        workflow,
        "_direct_benchmark",
        lambda **kwargs: PromotionPerformance("PRIMARY_A", 10.0, 1.5, 8.0, 30),
    )
    monkeypatch.setattr(
        workflow,
        "_shadow_performance_by_key",
        lambda path: {
            ("SOXL", "SHADOW_A"): {
                "simulated_allocation": 100.0,
                "primary_reference_quantity": shadow_quantity,
                "shadow_test_quantity": shadow_quantity,
                "sizing_basis": workflow.SHADOW_SIZING_BASIS,
                "net_pl": 12.0,
                "max_drawdown": -9.0,
                "gross_profit": 16.0,
                "gross_loss": -10.0,
                "profit_factor": 1.6,
                "trade_count": 25,
            }
        },
    )


def test_missing_veto_window_does_not_consume_monthly_review(monkeypatch, tmp_path) -> None:
    _patch_evidence(monkeypatch)
    monkeypatch.delenv(workflow.VETO_WINDOW_ENV, raising=False)
    state_path = tmp_path / "monthly.json"
    report = workflow.build_monthly_promotion_review(
        now="2026-09-02T15:00:00Z",
        monthly_state_path=state_path,
        review_report_path=tmp_path / "report.json",
        review_history_path=tmp_path / "history.json",
        lifecycle_path=tmp_path / "lifecycle.json",
    )
    assert report.rows[0].status == "VETO_WINDOW_NOT_CONFIGURED"
    assert not state_path.exists()


def test_quantity_mismatch_fails_closed_without_consuming_monthly_review(monkeypatch, tmp_path) -> None:
    _patch_evidence(monkeypatch, shadow_quantity=11.0)
    state_path = tmp_path / "monthly.json"
    report = workflow.build_monthly_promotion_review(
        now="2026-09-02T15:00:00Z",
        veto_window_days=3,
        monthly_state_path=state_path,
        review_report_path=tmp_path / "report.json",
        review_history_path=tmp_path / "history.json",
        lifecycle_path=tmp_path / "lifecycle.json",
    )
    assert report.rows[0].status == "SHADOW_QUANTITY_MISMATCH"
    assert report.rows[0].primary_reference_quantity == 12.5
    assert not state_path.exists()


def test_daily_cycle_counts_only_once_per_calendar_month(monkeypatch, tmp_path) -> None:
    _patch_evidence(monkeypatch)
    calls: list[str] = []

    def fake_review(**kwargs):
        calls.append(kwargs["underlying_symbol"])
        result = SimpleNamespace(qualified_strategy_id=None)
        return result, None

    monkeypatch.setattr(workflow, "review_and_queue_qualified_shadow", fake_review)
    state_path = tmp_path / "monthly.json"
    common = dict(
        veto_window_days=3,
        monthly_state_path=state_path,
        review_report_path=tmp_path / "report.json",
        review_history_path=tmp_path / "history.json",
        lifecycle_path=tmp_path / "lifecycle.json",
    )
    first = workflow.build_monthly_promotion_review(now="2026-09-02T15:00:00Z", **common)
    second = workflow.build_monthly_promotion_review(now="2026-09-03T15:00:00Z", **common)

    assert first.rows[0].status == "REVIEWED_NOT_QUALIFIED"
    assert first.rows[0].primary_reference_quantity == 12.5
    assert first.rows[0].evidence_basis == workflow.EVIDENCE_BASIS
    assert first.rows[0].normalization_basis == workflow.NORMALIZATION_BASIS
    assert second.rows[0].status == "ALREADY_REVIEWED_THIS_MONTH"
    assert calls == ["SOXL"]


def test_next_calendar_month_advances_review_again(monkeypatch, tmp_path) -> None:
    _patch_evidence(monkeypatch)
    calls: list[str] = []

    def fake_review(**kwargs):
        calls.append(kwargs["qualified_at"])
        return SimpleNamespace(qualified_strategy_id=None), None

    monkeypatch.setattr(workflow, "review_and_queue_qualified_shadow", fake_review)
    common = dict(
        veto_window_days=3,
        monthly_state_path=tmp_path / "monthly.json",
        review_report_path=tmp_path / "report.json",
        review_history_path=tmp_path / "history.json",
        lifecycle_path=tmp_path / "lifecycle.json",
    )
    workflow.build_monthly_promotion_review(now="2026-09-30T15:00:00Z", **common)
    workflow.build_monthly_promotion_review(now="2026-10-01T15:00:00Z", **common)
    assert len(calls) == 2

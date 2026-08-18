from __future__ import annotations

import json
from pathlib import Path

import pytest

import swing_trade_bot.tuesday_mapped_universe_workflow as workflow


def test_tuesday_workflow_runs_refresh_before_ranking(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_refresh(**kwargs):
        calls.append("refresh")
        return {
            "mapped_underlying_count": 2,
            "underlyings_with_component_evidence": 1,
            "underlyings_with_complete_component_evidence": 0,
        }

    def fake_review(**kwargs):
        calls.append("review")
        return {
            "mapped_underlying_count": 2,
            "selected_watchlist_count": 1,
            "selected_underlyings": ["NVDA"],
        }

    monkeypatch.setattr(workflow, "build_and_write_mapped_universe_evidence_refresh", fake_refresh)
    monkeypatch.setattr(workflow, "build_and_write_weekly_mapped_universe_review", fake_review)

    result = workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)

    assert calls == ["refresh", "review"]
    assert result["status"] == "COMPLETE"
    assert result["selected_underlyings"] == ["NVDA"]


def test_tuesday_workflow_fails_closed_if_refresh_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ranked = False

    def bad_refresh(**kwargs):
        raise RuntimeError("refresh failed")

    def fake_review(**kwargs):
        nonlocal ranked
        ranked = True
        return {}

    monkeypatch.setattr(workflow, "build_and_write_mapped_universe_evidence_refresh", bad_refresh)
    monkeypatch.setattr(workflow, "build_and_write_weekly_mapped_universe_review", fake_review)

    with pytest.raises(RuntimeError, match="refresh failed"):
        workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)

    assert ranked is False
    status = json.loads((tmp_path / workflow.STATUS_FILENAME).read_text(encoding="utf-8"))
    assert status["status"] == "FAILED"


def test_tuesday_workflow_is_paper_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        workflow,
        "build_and_write_mapped_universe_evidence_refresh",
        lambda **kwargs: {
            "mapped_underlying_count": 0,
            "underlyings_with_component_evidence": 0,
            "underlyings_with_complete_component_evidence": 0,
        },
    )
    monkeypatch.setattr(
        workflow,
        "build_and_write_weekly_mapped_universe_review",
        lambda **kwargs: {
            "mapped_underlying_count": 0,
            "selected_watchlist_count": 0,
            "selected_underlyings": [],
        },
    )

    result = workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)

    assert result["paper_trade_mode"] is True
    assert result["live_trading_enabled"] is False
    assert result["broker_execution_enabled"] is False
    assert result["order_placement_enabled"] is False
    assert result["capital_movement_enabled"] is False

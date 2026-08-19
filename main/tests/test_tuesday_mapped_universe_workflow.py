from __future__ import annotations

import json
from pathlib import Path

import pytest

import swing_trade_bot.tuesday_mapped_universe_workflow as workflow


def _patch_success(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    monkeypatch.setattr(workflow, "refresh_and_write_mapped_underlying_market_data", lambda **kwargs: calls.append("market") or {"mapped_underlying_count": 2, "current_market_data_count": 2})
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_quantitative_evidence", lambda **kwargs: calls.append("quantitative") or {"mapped_underlying_count": 2, "quantitatively_scored_count": 2})
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_fundamental_data", lambda **kwargs: calls.append("fundamental_data") or {"mapped_underlying_count": 2, "underlyings_with_fundamental_metrics": 2, "rows": [{"underlying_symbol": "NVDA", "metrics": {"revenue_growth_pct": 20, "earnings_growth_pct": 25, "operating_margin_pct": 30, "free_cash_flow_margin_pct": 20}}, {"underlying_symbol": "PLTR", "metrics": {"revenue_growth_pct": 15, "earnings_growth_pct": 20, "operating_margin_pct": 25, "free_cash_flow_margin_pct": 18}}]})
    monkeypatch.setattr(workflow, "build_mapped_underlying_fundamental_evidence", lambda **kwargs: calls.append("fundamental_score") or {"mapped_underlying_count": 2, "fundamentally_scored_count": 2, "rows": []})
    monkeypatch.setattr(workflow, "write_mapped_underlying_fundamental_evidence", lambda *args, **kwargs: calls.append("fundamental_write") or Path(kwargs.get("output_dir", ".")) / "mapped_underlying_fundamental_evidence.json")
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_news_refresh", lambda **kwargs: calls.append("news") or {"mapped_underlying_count": 2, "accepted_mention_count": 4, "errors": [], "rows": []})
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_intelligence_evidence", lambda **kwargs: calls.append("intelligence") or {"mapped_underlying_count": 2, "underlyings_with_market_intelligence": 2, "underlyings_with_conviction": 1, "rows": []})
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_market_regime_evidence", lambda **kwargs: calls.append("regime") or {"mapped_underlying_count": 2, "market_regime_support_score": 80.0, "rows": []})
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_portfolio_risk_evidence", lambda **kwargs: calls.append("portfolio_risk") or {"mapped_underlying_count": 2, "portfolio_risk_scored_count": 2, "rows": []})
    monkeypatch.setattr(workflow, "build_and_write_mapped_universe_evidence_refresh", lambda **kwargs: calls.append("refresh") or {"mapped_underlying_count": 2, "underlyings_with_component_evidence": 2, "underlyings_with_complete_component_evidence": 2})
    monkeypatch.setattr(workflow, "build_and_write_weekly_mapped_universe_review", lambda **kwargs: calls.append("review") or {"mapped_underlying_count": 2, "selected_watchlist_count": 1, "selected_underlyings": ["NVDA"]})


def test_tuesday_workflow_runs_all_seven_components_before_ranking(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _patch_success(monkeypatch, calls)
    result = workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path, data_dir=tmp_path / "data")
    assert calls == ["market", "quantitative", "fundamental_data", "fundamental_score", "fundamental_write", "news", "intelligence", "regime", "portfolio_risk", "refresh", "review"]
    assert result["status"] == "COMPLETE"
    assert result["selected_underlyings"] == ["NVDA"]


def test_tuesday_workflow_fails_closed_if_market_refresh_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    later_called = False
    def bad_market(**kwargs):
        raise RuntimeError("market refresh failed")
    def later(**kwargs):
        nonlocal later_called
        later_called = True
        return {}
    monkeypatch.setattr(workflow, "refresh_and_write_mapped_underlying_market_data", bad_market)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_quantitative_evidence", later)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_fundamental_data", later)
    monkeypatch.setattr(workflow, "build_mapped_underlying_fundamental_evidence", later)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_news_refresh", later)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_intelligence_evidence", later)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_market_regime_evidence", later)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_portfolio_risk_evidence", later)
    monkeypatch.setattr(workflow, "build_and_write_mapped_universe_evidence_refresh", later)
    monkeypatch.setattr(workflow, "build_and_write_weekly_mapped_universe_review", later)
    with pytest.raises(RuntimeError, match="market refresh failed"):
        workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)
    assert later_called is False
    status = json.loads((tmp_path / workflow.STATUS_FILENAME).read_text(encoding="utf-8"))
    assert status["status"] == "FAILED"


def test_tuesday_workflow_fails_closed_if_quantitative_evidence_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow, "refresh_and_write_mapped_underlying_market_data", lambda **kwargs: {"mapped_underlying_count": 1, "current_market_data_count": 1})
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_quantitative_evidence", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("quant failed")))
    with pytest.raises(RuntimeError, match="quant failed"):
        workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)


def test_tuesday_workflow_fails_closed_if_fundamental_data_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow, "refresh_and_write_mapped_underlying_market_data", lambda **kwargs: {"mapped_underlying_count": 1, "current_market_data_count": 1})
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_quantitative_evidence", lambda **kwargs: {"mapped_underlying_count": 1, "quantitatively_scored_count": 1})
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_fundamental_data", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("fundamental failed")))
    with pytest.raises(RuntimeError, match="fundamental failed"):
        workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)


def test_tuesday_workflow_fails_closed_if_news_refresh_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _patch_success(monkeypatch, calls)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_news_refresh", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("news failed")))
    with pytest.raises(RuntimeError, match="news failed"):
        workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)


def test_tuesday_workflow_fails_closed_if_intelligence_evidence_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _patch_success(monkeypatch, calls)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_intelligence_evidence", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("intelligence failed")))
    with pytest.raises(RuntimeError, match="intelligence failed"):
        workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)


def test_tuesday_workflow_fails_closed_if_regime_evidence_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _patch_success(monkeypatch, calls)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_market_regime_evidence", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("regime failed")))
    with pytest.raises(RuntimeError, match="regime failed"):
        workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)


def test_tuesday_workflow_fails_closed_if_portfolio_risk_evidence_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _patch_success(monkeypatch, calls)
    monkeypatch.setattr(workflow, "build_and_write_mapped_underlying_portfolio_risk_evidence", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("portfolio risk failed")))
    with pytest.raises(RuntimeError, match="portfolio risk failed"):
        workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)


def test_tuesday_workflow_is_paper_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    _patch_success(monkeypatch, calls)
    result = workflow.run_tuesday_mapped_universe_workflow(results_dir=tmp_path)
    assert result["paper_trade_mode"] is True
    assert result["live_trading_enabled"] is False
    assert result["broker_execution_enabled"] is False
    assert result["order_placement_enabled"] is False
    assert result["capital_movement_enabled"] is False

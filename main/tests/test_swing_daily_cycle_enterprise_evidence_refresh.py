from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from swing_trade_bot import swing_daily_cycle as cycle


def _runtime_config() -> dict:
    return {
        "runtime_evidence_refresh": {
            "enabled": True,
            "watchlist": {
                "candidates_path": "results/discovery_candidates_runtime.csv",
                "mentions_path": "results/discovery_mentions_runtime.csv",
                "financial_health_path": "results/discovery_financial_health_runtime.csv",
            },
            "portfolio_allocation": {
                "confidence_path": "results/confidence_report.csv",
                "strategy_recommendations_path": "results/strategy_recommendations.csv",
            },
            "paper_ledger": {
                "ledger_dir": "results/paper_ledger",
                "data_dir": "data",
            },
        },
        "opportunity_quality_input_path": "results/opportunity_quality_inputs.json",
        "decision_trace_evidence_path": "results/trace_evidence.json",
        "decision_trace_path": "results/trace.json",
    }


def test_enterprise_inputs_refresh_before_watchlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "results"
    output.mkdir()
    calls: list[tuple[str, dict]] = []

    def discovery(**kwargs):
        calls.append(("enterprise_discovery", kwargs))
        return {"paper_trade_mode": True}

    def financial(**kwargs):
        calls.append(("enterprise_financial_health", kwargs))
        return {"paper_trade_mode": True}

    def watchlist(*args, **kwargs):
        calls.append(("watchlist", {}))

    def stop_after_watchlist(**kwargs):
        raise RuntimeError("stop after watchlist-order assertion")

    monkeypatch.setattr(cycle, "refresh_enterprise_discovery_inputs", discovery)
    monkeypatch.setattr(cycle, "refresh_enterprise_financial_health_inputs", financial)
    monkeypatch.setattr(cycle, "_refresh_watchlist", watchlist)
    monkeypatch.setattr(cycle, "refresh_daily_committee_evidence", stop_after_watchlist)

    with pytest.raises(RuntimeError, match="stop after watchlist-order assertion"):
        cycle._produce_strategy_reports(
            tmp_path,
            output,
            _runtime_config(),
            "2026-09-04T14:00:00Z",
            [],
            [],
            lambda *args: None,
        )

    assert [name for name, _ in calls] == [
        "enterprise_discovery",
        "enterprise_financial_health",
        "watchlist",
    ]
    assert calls[0][1]["swing_root"] == tmp_path
    assert calls[1][1]["swing_root"] == tmp_path
    assert calls[1][1]["as_of"] == date(2026, 9, 4)


def test_enterprise_input_failure_blocks_watchlist_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "results"
    output.mkdir()
    calls: list[str] = []

    def discovery(**kwargs):
        calls.append("enterprise_discovery")
        raise FileNotFoundError("current enterprise discovery evidence missing")

    def financial(**kwargs):
        calls.append("enterprise_financial_health")

    def watchlist(*args, **kwargs):
        calls.append("watchlist")

    monkeypatch.setattr(cycle, "refresh_enterprise_discovery_inputs", discovery)
    monkeypatch.setattr(cycle, "refresh_enterprise_financial_health_inputs", financial)
    monkeypatch.setattr(cycle, "_refresh_watchlist", watchlist)

    errors: list[str] = []
    result = cycle._produce_strategy_reports(
        tmp_path,
        output,
        _runtime_config(),
        "2026-09-04T14:00:00Z",
        errors,
        [],
        lambda *args: None,
    )

    assert result is False
    assert calls == ["enterprise_discovery"]
    assert any("current enterprise discovery evidence missing" in error for error in errors)


def test_daily_cycle_config_uses_runtime_financial_health_and_preserves_safety_locks() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "configs/swing_daily_cycle.json").read_text(encoding="utf-8"))

    assert payload["runtime_evidence_refresh"]["watchlist"]["financial_health_path"] == (
        "results/discovery_financial_health_runtime.csv"
    )
    assert payload["paper_trade_mode"] is True
    assert payload["advisory_only"] is True
    assert payload["broker_execution_allowed"] is False
    assert payload["capital_movement_allowed"] is False

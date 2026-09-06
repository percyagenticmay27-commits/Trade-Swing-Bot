from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot import daily_committee_evidence_refresh as refresh


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_refresh_orders_entry_then_bootstrap_oq_then_thesis_then_final_oq(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    _write(results / "watchlist_report.json", {"rows": [{"underlying_symbol": "NVDA", "capacity_status": "ACTIVE"}]})
    _write(tmp_path / "configs/frozen_strategy_assignments.json", {"strategies": []})

    calls: list[str] = []

    def entry(**kwargs):
        calls.append("entry")
        _write(results / "entry_score_market_data_refresh.json", {"paper_trade_mode": True})
        _write(results / "entry_score_report.json", {"rows": [{"symbol": "NVDA", "entry_score": 70.0}]})
        (results / "entry_score_report.csv").write_text("symbol,entry_score\nNVDA,70\n", encoding="utf-8")
        return {"entry_score_pass_symbols": ["NVDA"]}

    def inputs(results_dir, output_path):
        calls.append("inputs")
        _write(Path(output_path), {"rows": [{"symbol": "NVDA"}]})
        return Path(output_path)

    def oq(**kwargs):
        calls.append("oq")
        _write(results / "opportunity_quality_report.json", {"rows": [{"symbol": "NVDA", "opportunity_quality_score": 82.854}]})
        (results / "opportunity_quality_report.csv").write_text("symbol\nNVDA\n", encoding="utf-8")
        (results / "opportunity_quality_report.md").write_text("# OQ\n", encoding="utf-8")

    def thesis(**kwargs):
        calls.append("thesis")
        payload = {"reviews": [{"underlying_symbol": "NVDA", "thesis_intact": True}]}
        _write(results / "thesis_monitor_v2_report.json", payload)
        (results / "thesis_monitor_v2_report.md").write_text("# Thesis\n", encoding="utf-8")
        return payload

    monkeypatch.setattr(refresh, "refresh_entry_score_evidence", entry)
    monkeypatch.setattr(refresh, "build_and_write_opportunity_quality_inputs", inputs)
    monkeypatch.setattr(refresh, "build_opportunity_quality_report", oq)
    monkeypatch.setattr(refresh, "build_and_write_thesis_monitor_v2", thesis)

    result = refresh.refresh_daily_committee_evidence(
        project_root=tmp_path,
        results_dir=results,
        quality_input_path=results / "opportunity_quality_inputs.json",
    )

    assert calls == ["entry", "inputs", "oq", "thesis", "inputs", "oq"]
    assert result["paper_trade_mode"] is True
    assert result["allocation_bypass_allowed"] is False
    assert result["thesis_intact_symbols"] == ["NVDA"]
    assert result["entry_score_policy_changed"] is False
    assert result["thesis_policy_changed"] is False
    assert result["opportunity_quality_policy_changed"] is False


def test_missing_watchlist_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        refresh.refresh_daily_committee_evidence(
            project_root=tmp_path,
            results_dir=tmp_path / "results",
            quality_input_path=tmp_path / "results/opportunity_quality_inputs.json",
        )


def test_live_mode_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        refresh.refresh_daily_committee_evidence(
            project_root=tmp_path,
            results_dir=tmp_path / "results",
            quality_input_path=tmp_path / "results/opportunity_quality_inputs.json",
            paper_trade_mode=False,
        )

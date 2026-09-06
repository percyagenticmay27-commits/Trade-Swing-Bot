from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot import swing_daily_cycle as cycle


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_refresh_uses_entry_thesis_pipeline_before_committee(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "results"
    output.mkdir()
    calls: list[str] = []

    config = {
        "opportunity_quality_input_path": "results/opportunity_quality_inputs.json",
        "decision_trace_evidence_path": "results/trace_evidence.json",
        "decision_trace_path": "results/trace.json",
        "runtime_evidence_refresh": {
            "enabled": True,
            "watchlist": {},
            "portfolio_allocation": {},
            "paper_ledger": {},
        },
    }

    def watchlist(*args, **kwargs):
        calls.append("watchlist")
        _write(output / "watchlist_report.json", {"rows": [{"underlying_symbol": "NVDA", "capacity_status": "ACTIVE"}]})

    def gate_refresh(**kwargs):
        calls.append("entry_thesis_oq")
        _write(output / "opportunity_quality_inputs.json", {"rows": [{"symbol": "NVDA", "entry_score": 70.0, "thesis_intact": True}]})
        _write(output / "opportunity_quality_report.json", {"rows": [{"symbol": "NVDA", "opportunity_quality_score": 82.854}]})
        return {
            "paper_trade_mode": True,
            "artifacts": [
                str(output / "entry_score_report.json"),
                str(output / "thesis_monitor_v2_report.json"),
                str(output / "opportunity_quality_inputs.json"),
                str(output / "opportunity_quality_report.json"),
            ],
        }

    def committee(results_dir, path, **kwargs):
        calls.append("committee")
        _write(
            Path(path),
            {
                "evaluation_cycle_id": "CYCLE",
                "symbol": "NVDA",
                "strategy_id": "SWING-001",
                "committee_steps": [
                    {
                        "committee_id": "ENTRY_COMMITTEE",
                        "sequence": 1,
                        "status": "PASS",
                        "reason_codes": [],
                        "evidence": {},
                        "source_artifacts": [],
                    }
                ],
                "final_status": "WAIT",
                "source_artifacts": [],
                "bias_audit": {},
            },
        )

    monkeypatch.setattr(cycle, "_refresh_watchlist", watchlist)
    monkeypatch.setattr(cycle, "refresh_daily_committee_evidence", gate_refresh)
    monkeypatch.setattr(cycle, "build_and_write_runtime_evidence", committee)
    monkeypatch.setattr(cycle, "build_committee_step", lambda **kwargs: kwargs)
    monkeypatch.setattr(cycle, "build_decision_trace", lambda **kwargs: {"trace": True})
    monkeypatch.setattr(cycle, "write_decision_trace", lambda payload, path: calls.append("trace") or _write(Path(path), payload))
    monkeypatch.setattr(cycle, "_refresh_allocation_and_paper_evidence", lambda *args, **kwargs: calls.append("allocation"))
    monkeypatch.setattr(cycle, "build_and_write_stock_performance_report", lambda *args, **kwargs: calls.append("stock"))
    monkeypatch.setattr(cycle, "build_and_write_weekly_stock_report", lambda *args, **kwargs: calls.append("weekly"))
    monkeypatch.setattr(cycle, "build_executive_dashboard", lambda *args, **kwargs: calls.append("executive"))
    monkeypatch.setattr(cycle, "build_monthly_command_center", lambda *args, **kwargs: calls.append("monthly"))

    errors: list[str] = []
    published: list[str] = []
    stages: list[tuple[str, bool]] = []
    result = cycle._produce_strategy_reports(
        tmp_path,
        output,
        config,
        "2026-09-03T02:45:00Z",
        errors,
        published,
        lambda name, passed, message: stages.append((name, passed)),
    )

    assert result is True
    assert errors == []
    assert calls[:4] == ["watchlist", "entry_thesis_oq", "committee", "trace"]
    assert calls.index("entry_thesis_oq") < calls.index("committee") < calls.index("allocation")
    assert ("OPPORTUNITY_QUALITY_INPUTS", True) in stages
    assert ("OPPORTUNITY_QUALITY", True) in stages
    assert str(output / "entry_score_report.json") in published
    assert str(output / "thesis_monitor_v2_report.json") in published


def test_runtime_gate_refresh_failure_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "results"
    output.mkdir()
    config = {
        "opportunity_quality_input_path": "results/opportunity_quality_inputs.json",
        "runtime_evidence_refresh": {"enabled": True},
    }
    monkeypatch.setattr(cycle, "_refresh_watchlist", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cycle,
        "refresh_daily_committee_evidence",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("current thesis evidence unavailable")),
    )

    errors: list[str] = []
    stages: list[tuple[str, bool]] = []
    result = cycle._produce_strategy_reports(
        tmp_path,
        output,
        config,
        "2026-09-03T02:45:00Z",
        errors,
        [],
        lambda name, passed, message: stages.append((name, passed)),
    )

    assert result is False
    assert any("current thesis evidence unavailable" in error for error in errors)
    assert ("OPPORTUNITY_QUALITY_INPUTS", False) in stages
    assert ("COMMITTEE_RUNTIME_EVIDENCE", False) in stages

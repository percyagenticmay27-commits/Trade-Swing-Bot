from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot import swing_daily_cycle as cycle


def _write_evidence(root: Path) -> None:
    path = root / "results/swing_committee_runtime_evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "evaluation_cycle_id": "CYCLE-1",
                "symbol": "SOXL",
                "strategy_id": "STRATEGY_A",
                "committee_steps": [
                    {
                        "committee_id": "DISCOVERY_COMMITTEE",
                        "sequence": 1,
                        "status": "PASS",
                        "reason_codes": ["EVIDENCE_PRESENT"],
                        "evidence": {"source_count": 2},
                        "source_artifacts": ["results/watchlist_report.json"],
                    }
                ],
                "final_status": "WAIT",
                "source_artifacts": ["results/watchlist_report.json"],
                "bias_audit": {},
            }
        ),
        encoding="utf-8",
    )


def _config() -> dict:
    return {
        "decision_trace_evidence_path": "results/swing_committee_runtime_evidence.json",
        "decision_trace_path": "results/swing_committee_decision_trace.json",
        "opportunity_quality_input_path": "results/opportunity_quality_inputs.json",
    }


def test_producers_execute_in_dependency_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_evidence(tmp_path)
    order: list[str] = []

    monkeypatch.setattr(
        cycle,
        "build_committee_step",
        lambda **kwargs: order.append("trace_step") or {"step": True},
    )
    monkeypatch.setattr(
        cycle,
        "build_decision_trace",
        lambda **kwargs: order.append("trace_build") or {"trace": True},
    )

    def write_trace(payload, path):
        order.append("trace_write")
        Path(path).write_text(json.dumps(payload), encoding="utf-8")
        return Path(path)

    def opportunity(**kwargs):
        order.append("opportunity")
        output = Path(kwargs["output_dir"])
        for suffix in ("csv", "json", "md"):
            (output / f"opportunity_quality_report.{suffix}").write_text(
                "report", encoding="utf-8"
            )

    def dashboard(results_dir, **kwargs):
        order.append("dashboard")
        Path(results_dir, "executive_dashboard.json").write_text(
            "{}", encoding="utf-8"
        )
        Path(results_dir, "executive_dashboard.md").write_text(
            "dashboard", encoding="utf-8"
        )

    def monthly(results_dir, **kwargs):
        order.append("monthly")
        Path(results_dir, "monthly_command_center.json").write_text(
            "{}", encoding="utf-8"
        )
        Path(results_dir, "monthly_command_center.md").write_text(
            "monthly", encoding="utf-8"
        )

    monkeypatch.setattr(cycle, "write_decision_trace", write_trace)
    monkeypatch.setattr(cycle, "build_opportunity_quality_report", opportunity)
    monkeypatch.setattr(
        cycle,
        "build_and_write_stock_performance_report",
        lambda *args, **kwargs: order.append("stock_performance"),
    )
    monkeypatch.setattr(
        cycle,
        "build_and_write_weekly_stock_report",
        lambda *args, **kwargs: order.append("weekly_stock"),
    )
    monkeypatch.setattr(cycle, "build_executive_dashboard", dashboard)
    monkeypatch.setattr(cycle, "build_monthly_command_center", monthly)

    errors: list[str] = []
    published: list[str] = []
    stages: list[str] = []
    ready = cycle._produce_strategy_reports(
        tmp_path,
        tmp_path / "results",
        _config(),
        "2026-07-30T12:00:00Z",
        errors,
        published,
        lambda name, passed, message: stages.append(name),
    )

    assert ready is True
    assert errors == []
    assert order == [
        "trace_step",
        "trace_build",
        "trace_write",
        "opportunity",
        "stock_performance",
        "weekly_stock",
        "dashboard",
        "monthly",
    ]
    assert stages == [
        "COMMITTEE_RUNTIME_EVIDENCE",
        "COMMITTEE_DECISION_TRACE",
        "OPPORTUNITY_QUALITY_INPUTS",
        "OPPORTUNITY_QUALITY",
        "STOCK_PERFORMANCE_REPORT",
        "WEEKLY_STOCK_REPORT",
        "EXECUTIVE_DASHBOARD",
        "MONTHLY_COMMAND_CENTER",
    ]


def test_missing_trace_evidence_blocks_all_downstream_producers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        cycle,
        "build_opportunity_quality_report",
        lambda **kwargs: calls.append("opportunity"),
    )
    monkeypatch.setattr(
        cycle,
        "build_executive_dashboard",
        lambda *args, **kwargs: calls.append("dashboard"),
    )
    monkeypatch.setattr(
        cycle,
        "build_monthly_command_center",
        lambda *args, **kwargs: calls.append("monthly"),
    )
    errors: list[str] = []
    ready = cycle._produce_strategy_reports(
        tmp_path,
        tmp_path / "results",
        _config(),
        "2026-07-30T12:00:00Z",
        errors,
        [],
        lambda *args: None,
    )
    assert ready is False
    assert calls == []
    assert errors
    assert not (tmp_path / "results/swing_committee_decision_trace.json").exists()


def test_opportunity_failure_blocks_dashboard_and_monthly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_evidence(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(cycle, "build_committee_step", lambda **kwargs: {})
    monkeypatch.setattr(cycle, "build_decision_trace", lambda **kwargs: {})
    monkeypatch.setattr(
        cycle,
        "write_decision_trace",
        lambda payload, path: Path(path).write_text("{}", encoding="utf-8"),
    )

    def fail_opportunity(**kwargs):
        calls.append("opportunity")
        raise FileNotFoundError("authentic input missing")

    monkeypatch.setattr(cycle, "build_opportunity_quality_report", fail_opportunity)
    monkeypatch.setattr(
        cycle,
        "build_executive_dashboard",
        lambda *args, **kwargs: calls.append("dashboard"),
    )
    monkeypatch.setattr(
        cycle,
        "build_monthly_command_center",
        lambda *args, **kwargs: calls.append("monthly"),
    )
    errors: list[str] = []
    ready = cycle._produce_strategy_reports(
        tmp_path,
        tmp_path / "results",
        _config(),
        "2026-07-30T12:00:00Z",
        errors,
        [],
        lambda *args: None,
    )
    assert ready is False
    assert calls == ["opportunity"]
    assert "authentic input missing" in errors[0]
    assert not (tmp_path / "results/opportunity_quality_report.json").exists()
    assert not (tmp_path / "results/executive_dashboard.json").exists()
    assert not (tmp_path / "results/monthly_command_center.json").exists()


def test_dashboard_failure_blocks_monthly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_evidence(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(cycle, "build_committee_step", lambda **kwargs: {})
    monkeypatch.setattr(cycle, "build_decision_trace", lambda **kwargs: {})
    monkeypatch.setattr(
        cycle,
        "write_decision_trace",
        lambda payload, path: Path(path).write_text("{}", encoding="utf-8"),
    )
    monkeypatch.setattr(
        cycle,
        "build_opportunity_quality_report",
        lambda **kwargs: calls.append("opportunity"),
    )
    monkeypatch.setattr(
        cycle,
        "build_and_write_stock_performance_report",
        lambda *args, **kwargs: calls.append("stock_performance"),
    )
    monkeypatch.setattr(
        cycle,
        "build_and_write_weekly_stock_report",
        lambda *args, **kwargs: calls.append("weekly_stock"),
    )

    def fail_dashboard(*args, **kwargs):
        calls.append("dashboard")
        raise ValueError("required dashboard evidence missing")

    monkeypatch.setattr(cycle, "build_executive_dashboard", fail_dashboard)
    monkeypatch.setattr(
        cycle,
        "build_monthly_command_center",
        lambda *args, **kwargs: calls.append("monthly"),
    )
    errors: list[str] = []
    ready = cycle._produce_strategy_reports(
        tmp_path,
        tmp_path / "results",
        _config(),
        "2026-07-30T12:00:00Z",
        errors,
        [],
        lambda *args: None,
    )
    assert ready is False
    assert calls == ["opportunity", "stock_performance", "weekly_stock", "dashboard"]
    assert "required dashboard evidence missing" in errors[0]
    assert not (tmp_path / "results/monthly_command_center.json").exists()

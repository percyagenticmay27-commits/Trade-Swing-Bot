from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from swing_trade_bot.swing_operational_health import (
    build_operational_health,
    latest_expected_run_utc,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed(results: Path, *, finished: str = "2026-08-14T22:31:00Z") -> None:
    _write(
        results / "operational_runtime_status.json",
        {
            "status": "SUCCESS",
            "authority_audit_status": "PASS",
            "cycle_exit_code": 0,
            "finished_at_utc": finished,
            "paper_trade_mode": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
            "order_placement_enabled": False,
            "capital_movement_enabled": False,
        },
    )
    _write(
        results / "swing_daily_cycle_report.json",
        {
            "cycle_status": "COMPLETE",
            "passed_stage_count": 15,
            "stage_count": 15,
            "registration_published": True,
        },
    )
    for relative in (
        "watchlist_report.json",
        "portfolio_allocations.json",
        "enterprise_strategy_kpis.json",
        "paper_ledger/paper_portfolio_summary.json",
        "paper_ledger/managed_trade_history.json",
    ):
        _write(results / relative, {})


def test_healthy_current_scheduled_runtime(tmp_path: Path) -> None:
    results = tmp_path / "results"
    _seed(results)
    report = build_operational_health(
        results,
        now_utc=datetime(2026, 8, 14, 23, 0, tzinfo=timezone.utc),
    )
    assert report["status"] == "HEALTHY"
    assert report["errors"] == []
    assert report["checks"]["scheduled_run_fresh"] is True
    assert report["checks"]["critical_runtime_files_writable"] is True


def test_failed_operational_status_is_unhealthy(tmp_path: Path) -> None:
    results = tmp_path / "results"
    _seed(results)
    payload = json.loads((results / "operational_runtime_status.json").read_text())
    payload["status"] = "FAILED"
    payload["cycle_exit_code"] = 1
    _write(results / "operational_runtime_status.json", payload)
    report = build_operational_health(
        results,
        now_utc=datetime(2026, 8, 14, 23, 0, tzinfo=timezone.utc),
    )
    assert report["status"] == "UNHEALTHY"
    assert any("not SUCCESS" in item for item in report["errors"])


def test_stale_weekday_run_is_unhealthy(tmp_path: Path) -> None:
    results = tmp_path / "results"
    _seed(results, finished="2026-08-13T22:31:00Z")
    report = build_operational_health(
        results,
        now_utc=datetime(2026, 8, 14, 23, 30, tzinfo=timezone.utc),
        grace_minutes=30,
    )
    assert report["status"] == "UNHEALTHY"
    assert report["checks"]["scheduled_run_fresh"] is False
    assert "Scheduled Swing runtime evidence is stale" in report["errors"]


def test_weekend_does_not_require_extra_run() -> None:
    # Saturday noon UTC still expects Friday's 18:30 Eastern run.
    expected = latest_expected_run_utc(
        datetime(2026, 8, 15, 16, 0, tzinfo=timezone.utc)
    )
    assert expected == datetime(2026, 8, 14, 22, 30, tzinfo=timezone.utc)


def test_incomplete_cycle_is_unhealthy(tmp_path: Path) -> None:
    results = tmp_path / "results"
    _seed(results)
    payload = json.loads((results / "swing_daily_cycle_report.json").read_text())
    payload["cycle_status"] = "BLOCKED"
    payload["passed_stage_count"] = 6
    payload["registration_published"] = False
    _write(results / "swing_daily_cycle_report.json", payload)
    report = build_operational_health(
        results,
        now_utc=datetime(2026, 8, 14, 23, 0, tzinfo=timezone.utc),
    )
    assert report["status"] == "UNHEALTHY"
    assert any("not COMPLETE" in item for item in report["errors"])


def test_unsafe_runtime_flags_fail_closed(tmp_path: Path) -> None:
    results = tmp_path / "results"
    _seed(results)
    payload = json.loads((results / "operational_runtime_status.json").read_text())
    payload["live_trading_enabled"] = True
    _write(results / "operational_runtime_status.json", payload)
    report = build_operational_health(
        results,
        now_utc=datetime(2026, 8, 14, 23, 0, tzinfo=timezone.utc),
    )
    assert report["status"] == "UNHEALTHY"
    assert report["checks"]["paper_safety"] is False


def test_missing_critical_runtime_file_warns_without_fabrication(tmp_path: Path) -> None:
    results = tmp_path / "results"
    _seed(results)
    (results / "enterprise_strategy_kpis.json").unlink()
    report = build_operational_health(
        results,
        now_utc=datetime(2026, 8, 14, 23, 0, tzinfo=timezone.utc),
    )
    assert "enterprise_strategy_kpis.json" in report["checks"]["critical_runtime_missing_files"]
    assert report["warnings"]

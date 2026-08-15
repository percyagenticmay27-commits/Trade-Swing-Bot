import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from swing_trade_bot.swing_strategy_alerts_report import (
    ADVISORY_ONLY,
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    build_swing_strategy_alerts_report,
    write_swing_strategy_alerts_report,
)


NOW = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)


def _write(root: Path, name: str, payload: dict) -> None:
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def _required(root: Path) -> None:
    _write(root, "enterprise_strategy_kpis.json", {
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "advisory_only": True,
        "generated_at": "2026-08-15T12:30:00Z",
        "position_count": 2,
        "warnings": [],
        "errors": [],
    })
    _write(root, "swing_daily_cycle_report.json", {
        "plugin_id": "SWING-001",
        "paper_trade_mode": True,
        "advisory_only": True,
        "generated_at_utc": "2026-08-15T12:30:00Z",
        "warnings": [],
        "errors": [],
    })


def test_zero_alert_result_discloses_completed_evaluation(tmp_path: Path) -> None:
    _required(tmp_path)
    report = build_swing_strategy_alerts_report(tmp_path, now=NOW)

    assert report["actionable_alert_count"] == 0
    assert report["alerts"] == []
    assert "no actionable alerts" in report["no_actionable_alerts_message"].lower()
    assert report["alert_authority_policy"] == "CURRENT_AUTHORITATIVE_EVIDENCE_ONLY"


def test_kpi_reportability_disclosures_are_not_actionable_alerts(tmp_path: Path) -> None:
    _required(tmp_path)
    payload = json.loads((tmp_path / "enterprise_strategy_kpis.json").read_text())
    payload["warnings"] = [
        "Win rate is not reportable until decided closed paper trades exist.",
        "Marked-to-market paper ledger is unavailable; allocated paper capital is used as a disclosed proxy.",
    ]
    _write(tmp_path, "enterprise_strategy_kpis.json", payload)

    report = build_swing_strategy_alerts_report(tmp_path, now=NOW)

    assert report["actionable_alert_count"] == 0
    assert report["alerts"] == []
    assert len(report["evidence_warnings"]) == 2
    assert all(item.startswith("KPI disclosure:") for item in report["evidence_warnings"])


def test_current_operational_error_becomes_advisory_alert(tmp_path: Path) -> None:
    _required(tmp_path)
    _write(tmp_path, "operational_health_report.json", {
        "paper_trade_mode": True,
        "generated_at_utc": "2026-08-15T12:45:00Z",
        "errors": ["Current scheduled cycle failed"],
        "warnings": [],
    })

    report = build_swing_strategy_alerts_report(tmp_path, now=NOW)

    assert report["actionable_alert_count"] == 1
    alert = report["alerts"][0]
    assert alert["severity"] == "ERROR"
    assert alert["evidence_source"] == "operational_health_report.json"
    assert alert["advisory_only"] is True


def test_stale_legacy_dashboard_flags_are_excluded(tmp_path: Path) -> None:
    _required(tmp_path)
    _write(tmp_path, "executive_dashboard.json", {
        "paper_trade_mode": True,
        "risk_flags": ["Exit review attention required"],
        "summary": {"active_positions": 0},
    })

    report = build_swing_strategy_alerts_report(tmp_path, now=NOW)

    assert report["alerts"] == []
    assert any("Legacy dashboard" in item for item in report["evidence_warnings"])
    evaluation = next(
        item for item in report["source_evaluations"]
        if item["source"] == "executive_dashboard.json"
    )
    assert evaluation["status"] == "EXCLUDED"


def test_required_stale_kpi_fails_closed(tmp_path: Path) -> None:
    _required(tmp_path)
    payload = json.loads((tmp_path / "enterprise_strategy_kpis.json").read_text())
    payload["generated_at"] = "2026-08-01T00:00:00Z"
    _write(tmp_path, "enterprise_strategy_kpis.json", payload)

    with pytest.raises(ValueError, match="not current"):
        build_swing_strategy_alerts_report(tmp_path, now=NOW)


def test_wrong_strategy_or_unsafe_kpi_is_rejected(tmp_path: Path) -> None:
    _required(tmp_path)
    payload = json.loads((tmp_path / "enterprise_strategy_kpis.json").read_text())
    payload["strategy_id"] = "DIVIDEND-001"
    _write(tmp_path, "enterprise_strategy_kpis.json", payload)
    with pytest.raises(ValueError, match="SWING-001"):
        build_swing_strategy_alerts_report(tmp_path, now=NOW)

    payload["strategy_id"] = "SWING-001"
    payload["paper_trade_mode"] = False
    _write(tmp_path, "enterprise_strategy_kpis.json", payload)
    with pytest.raises(ValueError, match="paper-only"):
        build_swing_strategy_alerts_report(tmp_path, now=NOW)


def test_json_csv_and_markdown_are_written(tmp_path: Path) -> None:
    _required(tmp_path)
    report = build_swing_strategy_alerts_report(tmp_path, now=NOW)
    paths = write_swing_strategy_alerts_report(report, tmp_path)

    assert all(path.exists() for path in paths)
    assert json.loads(paths[0].read_text())["strategy_id"] == "SWING-001"
    assert paths[1].read_text().startswith("strategy_id,symbol,alert_category")
    assert "no actionable alerts" in paths[2].read_text().lower()
    assert not list(tmp_path.glob("*.tmp"))


def test_paper_safety_constants_are_locked() -> None:
    assert PAPER_TRADE_MODE is True
    assert ADVISORY_ONLY is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False

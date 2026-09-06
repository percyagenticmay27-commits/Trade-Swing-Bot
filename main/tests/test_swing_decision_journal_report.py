import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from swing_trade_bot.swing_decision_journal_report import (
    BROKER_EXECUTION_ENABLED, CAPITAL_MOVEMENT_ENABLED, LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED, PAPER_TRADE_MODE, build_swing_decision_journal_report,
    write_swing_decision_journal_report,
)

NOW = datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc)


def _write(root: Path, name: str, payload: dict) -> None:
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def _required(root: Path, positions=None) -> None:
    _write(root, "enterprise_strategy_kpis.json", {"strategy_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "generated_at": "2026-08-15T14:30:00Z", "trade_analytics": {"open_positions": positions or []}})
    _write(root, "swing_daily_cycle_report.json", {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "generated_at_utc": "2026-08-15T14:30:00Z"})


def _committee(root: Path, timestamp="2026-08-15T14:30:00Z") -> None:
    steps = [{"committee_id": "DISCOVERY_COMMITTEE", "sequence": 1, "status": "PASS", "reason_codes": ["RANKED"], "evidence": {}, "source_artifacts": []}, {"committee_id": "ENTRY_COMMITTEE", "sequence": 3, "status": "HOLD", "reason_codes": ["ENTRY_EVIDENCE_PENDING"], "evidence": {}, "source_artifacts": []}]
    base = {"evaluation_cycle_id": "CYCLE-1", "symbol": "NBIS", "generated_at_utc": timestamp, "paper_trade_mode": True, "advisory_only": True, "committee_steps": steps, "final_status": "WAIT"}
    _write(root, "swing_committee_runtime_evidence.json", base)
    _write(root, "swing_committee_decision_trace.json", {**base, "plugin_id": "SWING-001", "decision_trace_id": "TRACE-1", "source_artifacts": ["results/watchlist_report.json"]})


def test_open_positions_are_hold_decisions_and_candidates_stay_separate(tmp_path: Path) -> None:
    _required(tmp_path, [{"symbol": "SOXL", "position_status": "OPEN", "active_strategy": "Strategy A"}, {"symbol": "TQQQ", "position_status": "OPEN", "active_strategy": "Strategy A"}])
    _committee(tmp_path)
    report = build_swing_decision_journal_report(tmp_path, now=NOW)
    assert [row["symbol"] for row in report["position_decisions"]] == ["SOXL", "TQQQ"]
    assert {row["current_decision"] for row in report["position_decisions"]} == {"HOLD"}
    assert report["candidate_decisions"][0]["current_decision"] == "WAITING_FOR_ENTRY"
    assert report["candidate_decisions"][0]["symbol"] == "NBIS"



def test_in_flight_kpi_payload_is_used_before_kpi_file_exists(tmp_path: Path) -> None:
    _write(tmp_path, "swing_daily_cycle_report.json", {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "generated_at_utc": "2026-08-15T14:30:00Z"})
    kpi = {"strategy_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "generated_at": "2026-08-15T14:30:00Z", "trade_analytics": {"open_positions": [{"symbol": "SOXL", "position_status": "OPEN", "active_strategy": "Strategy A"}]}}

    report = build_swing_decision_journal_report(tmp_path, kpi_payload=kpi, now=NOW)

    assert report["position_decisions"][0]["symbol"] == "SOXL"
    assert report["position_decisions"][0]["current_decision"] == "HOLD"
    assert not (tmp_path / "enterprise_strategy_kpis.json").exists()


def test_committee_timeline_is_deterministic(tmp_path: Path) -> None:
    _required(tmp_path); _committee(tmp_path)
    report = build_swing_decision_journal_report(tmp_path, now=NOW)
    assert [row["sequence"] for row in report["candidate_decisions"][0]["timeline"]] == [1, 3]


def test_stale_committee_evidence_is_excluded_not_relabelled(tmp_path: Path) -> None:
    _required(tmp_path); _committee(tmp_path, "2026-07-30T12:00:00Z")
    report = build_swing_decision_journal_report(tmp_path, now=NOW)
    assert report["candidate_decisions"] == []
    assert any("STALE" in item for item in report["evidence_warnings"])


def test_rebalance_buy_sell_is_never_consumed(tmp_path: Path) -> None:
    _required(tmp_path)
    _write(tmp_path, "rebalance_actions.json", {"actions": [{"symbol": "SOXL", "action": "SELL"}, {"symbol": "BEX", "action": "BUY"}]})
    report = build_swing_decision_journal_report(tmp_path, now=NOW)
    assert report["decisions"] == []
    assert report["excluded_planning_sources"] == ["results/rebalance_actions.json"]
    assert "no reportable decisions" in report["no_decisions_message"].lower()


def test_mismatched_committee_identity_fails_closed(tmp_path: Path) -> None:
    _required(tmp_path); _committee(tmp_path)
    payload = json.loads((tmp_path / "swing_committee_decision_trace.json").read_text())
    payload["symbol"] = "AMD"
    _write(tmp_path, "swing_committee_decision_trace.json", payload)
    with pytest.raises(ValueError, match="symbol do not match"):
        build_swing_decision_journal_report(tmp_path, now=NOW)


def test_json_and_markdown_are_atomic(tmp_path: Path) -> None:
    _required(tmp_path)
    report = build_swing_decision_journal_report(tmp_path, now=NOW)
    paths = write_swing_decision_journal_report(report, tmp_path)
    assert all(path.exists() for path in paths)
    assert json.loads(paths[0].read_text())["strategy_id"] == "SWING-001"
    assert not list(tmp_path.glob("*.tmp"))



def test_kpi_command_wires_decision_journal_publication() -> None:
    source = Path("publish_enterprise_strategy_kpis_v21.py").read_text(encoding="utf-8")
    assert "build_swing_decision_journal_report" in source
    assert "write_swing_decision_journal_report" in source
    assert 'payload["decision_journal"] = decision_journal' in source
    assert 'payload["dashboard_sections"]["decisions"] = decision_journal' in source
    assert '"swing_decision_journal_report"' in source


def test_paper_safety_constants_are_locked() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False

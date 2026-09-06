from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot import swing_operational_runtime as runtime


def _write_inputs(root: Path) -> None:
    results = root / "results"
    ledger = results / "paper_ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    (results / "enterprise_strategy_kpis.json").write_text(json.dumps({
        "strategy_id": "SWING-001", "allocated_capital": 4500.0,
        "allocation_source": "AI_CIO_ENTERPRISE_EVIDENCE",
        "opportunity_quality": 15.458, "watchlist_count": 1,
        "position_count": 1, "win_rate_percent": None,
        "paper_trade_mode": True, "live_trading_enabled": False,
        "broker_execution_enabled": False, "order_placement_enabled": False,
        "capital_movement_enabled": False,
    }), encoding="utf-8")
    (results / "opportunity_quality_report.json").write_text(json.dumps({"rows": [{"opportunity_quality_score": 15.458}]}), encoding="utf-8")
    (results / "watchlist_report.json").write_text(json.dumps({"freshness_status": "CURRENT_CYCLE", "rows": [{}]}), encoding="utf-8")
    (results / "swing_committee_runtime_evidence.json").write_text(json.dumps({"committee_steps": [
        {"committee_id": "OPPORTUNITY_COMMITTEE", "evidence": {"opportunity_quality_score": 15.458}},
        {"committee_id": "ENTRY_COMMITTEE", "evidence": {"entry_score": 0.0}},
    ]}), encoding="utf-8")
    (ledger / "paper_portfolio_summary.json").write_text(json.dumps({"position_count": 1, "portfolio_value": 4525.52, "unrealized_pnl": 25.52}), encoding="utf-8")
    (ledger / "paper_portfolio_positions.json").write_text(json.dumps({"positions": [{"symbol": "SOXL"}]}), encoding="utf-8")
    (ledger / "paper_performance.json").write_text(json.dumps({"closed_trade_count": 0, "win_rate_percent": None}), encoding="utf-8")
    (results / "market_data_refresh_status.json").write_text(json.dumps({"status": "AVAILABLE"}), encoding="utf-8")


def test_success_status(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    assert runtime.run_operational_cycle(root=tmp_path, run_cycle=lambda: 0) == 0
    status = json.loads((tmp_path / "results/operational_runtime_status.json").read_text())
    assert status["status"] == "SUCCESS"
    assert status["authority_audit_status"] == "PASS"
    assert not (tmp_path / "results/operational_runtime.lock").exists()


def test_cycle_failure_is_reported(tmp_path: Path) -> None:
    assert runtime.run_operational_cycle(root=tmp_path, run_cycle=lambda: 9) == 9
    status = json.loads((tmp_path / "results/operational_runtime_status.json").read_text())
    assert status["status"] == "FAILED"
    assert status["cycle_exit_code"] == 9


def test_audit_failure_is_reported(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    path = tmp_path / "results/enterprise_strategy_kpis.json"
    payload = json.loads(path.read_text())
    payload["win_rate_percent"] = 45.0
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert runtime.run_operational_cycle(root=tmp_path, run_cycle=lambda: 0) == 1
    status = json.loads((tmp_path / "results/operational_runtime_status.json").read_text())
    assert status["authority_audit_status"] == "FAIL"


def test_existing_lock_blocks_overlap(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir(parents=True)
    (results / "operational_runtime.lock").write_text("existing\n", encoding="utf-8")
    called = []
    assert runtime.run_operational_cycle(root=tmp_path, run_cycle=lambda: called.append(True) or 0) == 75
    assert called == []

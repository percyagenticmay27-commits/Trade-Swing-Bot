from __future__ import annotations

import csv
from pathlib import Path

from swing_trade_bot.user_veto_control import (
    active_vetoes,
    append_veto_event,
    apply_active_vetoes_to_runtime_candidates,
    load_veto_ledger,
    symbol_is_vetoed,
)


def _runtime(root: Path) -> Path:
    path = root / "results/discovery_candidates_runtime.csv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "underlying_symbol,leveraged_symbol,status,paper_return,win_rate,profit_factor,number_of_trades,trading_days,days_in_status,earnings_stability_score,leveraged_vehicle_exists,themes\n"
        "NVDA,NVDX,DISCOVERY,0,0,0,0,0,0,50,true,Semiconductors\n",
        encoding="utf-8",
    )
    return path


def test_absence_of_veto_does_not_block_normal_progression(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    report = apply_active_vetoes_to_runtime_candidates(root=tmp_path)
    assert report["approval_required"] is False
    assert report["absence_of_veto_allows_normal_progression"] is True
    assert report["active_veto_count"] == 0
    with runtime.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["leveraged_vehicle_exists"] == "true"


def test_active_veto_blocks_runtime_progression_without_deleting_mapping(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    ledger = tmp_path / "results/user_veto_ledger.json"
    append_veto_event(
        ledger,
        symbol="NVDA",
        action="VETO",
        rationale="User does not want this candidate progressed this week",
        operator="USER",
        timestamp="2026-08-18T15:00:00Z",
    )
    report = apply_active_vetoes_to_runtime_candidates(root=tmp_path)
    assert report["runtime_blocked_candidates"] == ["NVDA"]
    with runtime.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["leveraged_symbol"] == "NVDX"
    assert row["leveraged_vehicle_exists"] == "false"


def test_release_removes_veto_and_normal_autonomy_resumes(tmp_path: Path) -> None:
    _runtime(tmp_path)
    ledger = tmp_path / "results/user_veto_ledger.json"
    append_veto_event(ledger, symbol="NVDA", action="VETO", timestamp="2026-08-18T15:00:00Z")
    append_veto_event(ledger, symbol="NVDA", action="RELEASE", timestamp="2026-08-18T16:00:00Z")
    assert active_vetoes(load_veto_ledger(ledger)) == {}
    assert symbol_is_vetoed("NVDA", ledger_path=ledger) is False
    report = apply_active_vetoes_to_runtime_candidates(root=tmp_path)
    assert report["active_veto_count"] == 0


def test_veto_history_is_append_only_audit_evidence(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    append_veto_event(ledger, symbol="NVDA", action="VETO", rationale="risk", timestamp="2026-08-18T15:00:00Z")
    append_veto_event(ledger, symbol="NVDA", action="RELEASE", rationale="released", timestamp="2026-08-18T16:00:00Z")
    payload = load_veto_ledger(ledger)
    assert [row["action"] for row in payload["events"]] == ["VETO", "RELEASE"]
    assert payload["events"][0]["rationale"] == "risk"
    assert payload["approval_required"] is False


def test_no_manual_approval_or_broker_execution_is_introduced() -> None:
    import swing_trade_bot.user_veto_control as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    assert "pending_manual_review" not in source
    assert "manual_approval_required" not in source
    for forbidden in ("place_order", "submit_order", "execute_trade", "capital_movement_enabled"):
        assert forbidden not in source

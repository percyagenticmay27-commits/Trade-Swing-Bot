import json
from pathlib import Path

import pytest

from swing_trade_bot.swing_committee_runtime_evidence import (
    build_and_write_runtime_evidence,
    build_runtime_evidence,
)


def _watchlist(tmp_path: Path) -> None:
    (tmp_path / "watchlist_report.json").write_text(json.dumps({"rows": [
        {"underlying_symbol": "LOWER", "leveraged_symbol": "LOWX", "capacity_status": "ACTIVE", "watchlist_status": "WATCHLIST", "watchlist_rank": 1, "composite_score": 99},
        {"underlying_symbol": "TOP", "leveraged_symbol": "TOPX", "capacity_status": "ACTIVE", "watchlist_status": "WATCHLIST", "high_priority_rank": 1, "composite_score": 80},
        {"underlying_symbol": "REMOVED", "capacity_status": "REMOVED", "watchlist_status": "REMOVED", "high_priority_rank": 1, "composite_score": 100},
    ]}), encoding="utf-8")


def _quality(tmp_path: Path, *, score: float, entry_score: float | None = None, thesis_intact: bool | None = None) -> None:
    row = {"symbol": "TOP", "opportunity_quality_score": score}
    if entry_score is not None:
        row["entry_score"] = entry_score
    if thesis_intact is not None:
        row["thesis_intact"] = thesis_intact
    (tmp_path / "opportunity_quality_report.json").write_text(json.dumps({"rows": [row]}), encoding="utf-8")


def test_selects_highest_priority_active_candidate(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    result = build_runtime_evidence(tmp_path, generated_at_utc="2026-07-30T12:00:00Z")
    assert result["symbol"] == "TOP"
    assert result["committee_steps"][0]["status"] == "PASS"
    assert result["committee_steps"][0]["evidence"]["high_priority_rank"] == 1


def test_missing_scores_are_hold_not_invented(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    result = build_runtime_evidence(tmp_path)
    assert result["committee_steps"][1]["status"] == "HOLD"
    assert result["committee_steps"][1]["evidence"]["score_available"] is False
    assert result["committee_steps"][2]["status"] == "HOLD"
    assert result["final_status"] == "WAIT"


def test_fresh_opportunity_quality_reaches_opportunity_committee(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _quality(tmp_path, score=15.458, entry_score=0.0)
    result = build_runtime_evidence(tmp_path)
    opportunity = result["committee_steps"][1]
    assert opportunity["status"] == "FAIL"
    assert opportunity["evidence"]["score_available"] is True
    assert opportunity["evidence"]["opportunity_quality_score"] == 15.458
    assert opportunity["evidence"]["score_source"] == "results/opportunity_quality_report.json"
    assert result["committee_steps"][2]["status"] == "SKIPPED"
    assert result["final_status"] == "REJECTED"


def test_entry_committee_consumes_current_entry_score_when_available(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _quality(tmp_path, score=82.0, entry_score=75.0, thesis_intact=True)
    result = build_runtime_evidence(tmp_path)
    entry = result["committee_steps"][2]
    assert entry["status"] == "PASS"
    assert entry["evidence"]["entry_score"] == 75.0
    assert entry["evidence"]["entry_score_source"] == "results/opportunity_quality_report.json"
    portfolio = result["committee_steps"][3]
    assert portfolio["status"] == "PASS"
    assert portfolio["evidence"]["allocation_percent"] is None
    assert portfolio["evidence"]["allocation_pending"] is True
    assert result["final_status"] == "ELIGIBLE_FOR_ALLOCATION"


def test_missing_entry_score_remains_truthful_hold(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _quality(tmp_path, score=82.0, thesis_intact=True)
    result = build_runtime_evidence(tmp_path)
    entry = result["committee_steps"][2]
    assert entry["status"] == "HOLD"
    assert entry["evidence"]["entry_score"] is None
    assert entry["evidence"]["entry_score_source"] is None


def test_opportunity_rejection_skips_entry_and_portfolio(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _quality(tmp_path, score=60, entry_score=90, thesis_intact=True)
    result = build_runtime_evidence(tmp_path)
    assert result["committee_steps"][1]["status"] == "FAIL"
    assert result["committee_steps"][2]["status"] == "SKIPPED"
    assert result["committee_steps"][3]["status"] == "SKIPPED"
    assert result["final_status"] == "REJECTED"


def test_old_quality_inputs_cannot_override_fresh_opportunity_score(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _quality(tmp_path, score=15.458, entry_score=0.0)
    (tmp_path / "opportunity_quality_inputs.json").write_text(
        json.dumps({"rows": [{"symbol": "TOP", "opportunity_quality_score": 99, "entry_score": 99, "thesis_intact": True}]}),
        encoding="utf-8",
    )
    result = build_runtime_evidence(tmp_path)
    assert result["committee_steps"][1]["evidence"]["opportunity_quality_score"] == 15.458
    assert result["committee_steps"][1]["status"] == "FAIL"


def test_writes_safe_five_committee_payload(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    output = build_and_write_runtime_evidence(tmp_path)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["paper_trade_mode"] is True
    assert payload["broker_execution_allowed"] is False
    assert len(payload["committee_steps"]) == 5


def test_missing_watchlist_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_runtime_evidence(tmp_path)


def test_live_mode_is_rejected(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    with pytest.raises(ValueError):
        build_runtime_evidence(tmp_path, paper_trade_mode=False)

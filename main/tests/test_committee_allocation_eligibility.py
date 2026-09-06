import json
from pathlib import Path

import pytest

from swing_trade_bot.committee_allocation_eligibility import (
    build_and_write_committee_allocation_eligibility,
    build_committee_allocation_eligibility,
    load_eligible_symbols,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _watchlist(tmp_path: Path) -> None:
    _write(tmp_path / "watchlist_report.json", {"rows": [
        {"underlying_symbol": "NFLX", "leveraged_symbol": "NFLU", "capacity_status": "ACTIVE", "watchlist_status": "WATCHLIST"},
        {"underlying_symbol": "NVDA", "leveraged_symbol": "NVDX", "capacity_status": "ACTIVE", "watchlist_status": "HIGH"},
        {"underlying_symbol": "OLD", "capacity_status": "REMOVED", "watchlist_status": "REMOVED"},
    ]})


def test_only_opportunity_and_entry_approved_candidates_are_eligible(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _write(tmp_path / "opportunity_quality_report.json", {"rows": [
        {"symbol": "NFLX", "opportunity_quality_score": 82, "entry_score": 75, "thesis_intact": True},
        {"symbol": "NVDA", "opportunity_quality_score": 90, "entry_score": 60, "thesis_intact": True},
    ]})
    payload = build_committee_allocation_eligibility(tmp_path)
    assert payload["eligible_symbols"] == ["NFLX"]
    rows = {row["symbol"]: row for row in payload["rows"]}
    assert rows["NFLX"]["final_status"] == "ELIGIBLE_FOR_ALLOCATION"
    assert rows["NVDA"]["final_status"] == "REJECTED"
    assert "OLD" not in rows


def test_opportunity_failure_prevents_entry_eligibility(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _write(tmp_path / "opportunity_quality_report.json", {"rows": [
        {"symbol": "NFLX", "opportunity_quality_score": 68.2305, "entry_score": 99, "thesis_intact": True},
    ]})
    payload = build_committee_allocation_eligibility(tmp_path)
    row = next(row for row in payload["rows"] if row["symbol"] == "NFLX")
    assert row["eligible_for_allocation"] is False
    assert row["reason_code"] == "OPPORTUNITY_THRESHOLD_NOT_MET"
    assert "NFLX" not in payload["eligible_symbols"]


def test_missing_entry_score_waits_and_is_not_invented(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _write(tmp_path / "opportunity_quality_report.json", {"rows": [
        {"symbol": "NFLX", "opportunity_quality_score": 82, "thesis_intact": True},
    ]})
    payload = build_committee_allocation_eligibility(tmp_path)
    row = next(row for row in payload["rows"] if row["symbol"] == "NFLX")
    assert row["entry_score"] is None
    assert row["final_status"] == "WAIT"
    assert row["eligible_for_allocation"] is False


def test_current_inputs_can_supply_entry_evidence_without_overriding_opportunity(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _write(tmp_path / "opportunity_quality_report.json", {"rows": [
        {"symbol": "NFLX", "opportunity_quality_score": 82},
    ]})
    _write(tmp_path / "opportunity_quality_inputs.json", {"rows": [
        {"symbol": "NFLX", "entry_score": 77, "thesis_intact": True},
    ]})
    payload = build_committee_allocation_eligibility(tmp_path)
    assert payload["eligible_symbols"] == ["NFLX"]


def test_writes_paper_only_artifact_and_loads_symbols(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _write(tmp_path / "opportunity_quality_report.json", {"rows": [
        {"symbol": "NFLX", "opportunity_quality_score": 82, "entry_score": 75, "thesis_intact": True},
    ]})
    output = tmp_path / "committee_allocation_eligibility.json"
    build_and_write_committee_allocation_eligibility(tmp_path, output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["paper_trade_mode"] is True
    assert payload["broker_execution_enabled"] is False
    assert load_eligible_symbols(output) == {"NFLX"}


def test_live_mode_is_rejected(tmp_path: Path) -> None:
    _watchlist(tmp_path)
    _write(tmp_path / "opportunity_quality_report.json", {"rows": []})
    with pytest.raises(ValueError):
        build_committee_allocation_eligibility(tmp_path, paper_trade_mode=False)

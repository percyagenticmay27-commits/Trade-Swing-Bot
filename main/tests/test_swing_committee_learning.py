from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from swing_trade_bot.swing_committee_learning import (
    COMMITTEES,
    append_unique_observations,
    build_committee_learning_report,
    build_committee_observation,
    evidence_is_sufficient,
    generate_learning_proposals,
    load_committee_learning_config,
    summarize_committee_learning,
    validate_committee_learning_config,
    write_committee_learning_report,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "swing_committee_learning.json"


@pytest.fixture()
def config() -> dict:
    return load_committee_learning_config(CONFIG)


def observation(committee_id: str, index: int = 0, *, compliant: bool = True, complete: bool = True, mae: float = -1.0) -> dict:
    return build_committee_observation(
        decision_trace_id=f"TRACE-{committee_id}-{index}",
        committee_id=committee_id,
        strategy_id="STRATEGY_A",
        decision_status="PASS",
        decision_quality={"policy_compliant": compliant, "evidence_complete": complete},
        outcome_quality={
            "return_percent": 2.0,
            "maximum_favorable_excursion_percent": 4.0,
            "maximum_adverse_excursion_percent": mae,
        },
        measurement_horizon="5_TRADING_DAYS",
        source_artifacts=["results/trace.json", "results/outcome.json"],
        observed_at_utc="2026-07-27T20:00:00Z",
    )


def full_observations(count: int = 10) -> list[dict]:
    return [observation(committee, i) for committee in COMMITTEES for i in range(count)]


def test_config_loads(config):
    assert config["plugin_id"] == "SWING-001"


def test_config_is_valid(config):
    assert validate_committee_learning_config(config).valid


@pytest.mark.parametrize("field,bad", [
    ("paper_trade_mode", False),
    ("advisory_only", False),
    ("append_only", False),
    ("automatic_policy_change_allowed", True),
    ("human_approval_required", False),
    ("broker_execution_allowed", True),
    ("capital_movement_allowed", True),
])
def test_config_safety_locks(config, field, bad):
    changed = copy.deepcopy(config)
    changed[field] = bad
    assert not validate_committee_learning_config(changed).valid


def test_committee_order_is_frozen(config):
    assert tuple(config["committee_sequence"]) == COMMITTEES


def test_changed_committee_order_rejected(config):
    changed = copy.deepcopy(config)
    changed["committee_sequence"].reverse()
    assert not validate_committee_learning_config(changed).valid


@pytest.mark.parametrize("field,bad", [
    ("completed_decision_traces", 29),
    ("history_months", 5),
    ("observations_per_committee", 9),
])
def test_minimum_evidence_is_locked(config, field, bad):
    changed = copy.deepcopy(config)
    changed["minimum_evidence"][field] = bad
    assert not validate_committee_learning_config(changed).valid


def test_observation_id_is_deterministic():
    assert observation("ENTRY_COMMITTEE")["observation_id"] == observation("ENTRY_COMMITTEE")["observation_id"]


def test_observation_changes_when_outcome_changes():
    first = observation("ENTRY_COMMITTEE", mae=-1.0)
    second = observation("ENTRY_COMMITTEE", mae=-8.0)
    assert first["observation_id"] != second["observation_id"]


def test_observation_is_append_only_and_safe():
    row = observation("ENTRY_COMMITTEE")
    assert row["append_only"] is True
    assert row["paper_trade_mode"] is True
    assert row["advisory_only"] is True
    assert row["automatic_policy_change_allowed"] is False


def test_unknown_committee_rejected():
    with pytest.raises(ValueError):
        build_committee_observation(
            decision_trace_id="TRACE-1", committee_id="UNKNOWN", strategy_id="STRATEGY_A",
            decision_status="PASS", decision_quality={}, outcome_quality={},
            measurement_horizon="5_TRADING_DAYS", source_artifacts=[]
        )


def test_missing_trace_id_rejected():
    with pytest.raises(ValueError):
        build_committee_observation(
            decision_trace_id="", committee_id="ENTRY_COMMITTEE", strategy_id="STRATEGY_A",
            decision_status="PASS", decision_quality={}, outcome_quality={},
            measurement_horizon="5_TRADING_DAYS", source_artifacts=[]
        )


def test_append_unique_observations_deduplicates():
    row = observation("ENTRY_COMMITTEE")
    assert len(append_unique_observations([row], [row])) == 1


def test_append_unique_observations_preserves_order():
    first = observation("ENTRY_COMMITTEE", 1)
    second = observation("ENTRY_COMMITTEE", 2)
    combined = append_unique_observations([first], [second])
    assert [row["observation_id"] for row in combined] == [first["observation_id"], second["observation_id"]]


def test_observation_without_record_key_rejected():
    with pytest.raises(ValueError):
        append_unique_observations([], [{"observation_id": "BAD"}])


def test_summaries_keep_decision_and_outcome_quality_separate():
    summary = summarize_committee_learning([observation("ENTRY_COMMITTEE")])[0]
    assert summary["policy_compliance_rate_percent"] == 100.0
    assert summary["average_return_percent"] == 2.0


def test_summary_tracks_evidence_completeness():
    rows = [observation("ENTRY_COMMITTEE", 1, complete=True), observation("ENTRY_COMMITTEE", 2, complete=False)]
    assert summarize_committee_learning(rows)[0]["evidence_completeness_rate_percent"] == 50.0


def test_evidence_insufficient_below_30_traces():
    assert not evidence_is_sufficient(completed_decision_traces=29, history_months=6, committee_summaries=summarize_committee_learning(full_observations()))


def test_evidence_insufficient_below_6_months():
    assert not evidence_is_sufficient(completed_decision_traces=30, history_months=5, committee_summaries=summarize_committee_learning(full_observations()))


def test_evidence_insufficient_when_one_committee_has_too_few_observations():
    rows = full_observations()
    rows = [row for row in rows if row["committee_id"] != "EXIT_COMMITTEE"] + [observation("EXIT_COMMITTEE", i) for i in range(9)]
    assert not evidence_is_sufficient(completed_decision_traces=30, history_months=6, committee_summaries=summarize_committee_learning(rows))


def test_evidence_sufficient_at_locked_minimums():
    assert evidence_is_sufficient(completed_decision_traces=30, history_months=6, committee_summaries=summarize_committee_learning(full_observations()))


def test_no_proposals_when_evidence_is_insufficient():
    assert generate_learning_proposals([], evidence_sufficient=False) == []


def test_process_review_proposal_for_policy_noncompliance():
    rows = full_observations()
    rows[0] = observation("DISCOVERY_COMMITTEE", 0, compliant=False)
    proposals = generate_learning_proposals(summarize_committee_learning(rows), evidence_sufficient=True)
    assert any(p["proposal_type"] == "COMMITTEE_PROCESS_REVIEW" for p in proposals)


def test_evidence_review_proposal_for_incomplete_evidence():
    rows = [observation(committee, i, complete=False) for committee in COMMITTEES for i in range(10)]
    proposals = generate_learning_proposals(summarize_committee_learning(rows), evidence_sufficient=True)
    assert any(p["proposal_type"] == "EVIDENCE_SOURCE_REVIEW" for p in proposals)


def test_entry_threshold_review_for_adverse_excursion():
    rows = [observation(committee, i, mae=-7.0 if committee == "ENTRY_COMMITTEE" else -1.0) for committee in COMMITTEES for i in range(10)]
    proposals = generate_learning_proposals(summarize_committee_learning(rows), evidence_sufficient=True)
    assert any(p["proposal_type"] == "THRESHOLD_REVIEW" and p["target"] == "ENTRY_COMMITTEE" for p in proposals)


def test_good_evidence_produces_no_change_proposal():
    proposals = generate_learning_proposals(summarize_committee_learning(full_observations()), evidence_sufficient=True)
    assert [p["proposal_type"] for p in proposals] == ["NO_CHANGE"]


def test_all_proposals_require_human_approval():
    proposals = generate_learning_proposals(summarize_committee_learning(full_observations()), evidence_sufficient=True)
    assert all(p["requires_human_approval"] is True for p in proposals)
    assert all(p["automatic_policy_change"] is False for p in proposals)


def test_observation_only_report_before_minimum_evidence():
    report = build_committee_learning_report(observations=full_observations(), completed_decision_traces=29, history_months=6)
    assert report["learning_status"] == "OBSERVATION_ONLY"
    assert report["proposal_count"] == 0
    assert report["warnings"]


def test_report_becomes_eligible_for_review():
    report = build_committee_learning_report(observations=full_observations(), completed_decision_traces=30, history_months=6)
    assert report["learning_status"] == "ELIGIBLE_FOR_REVIEW"
    assert report["evidence_summary"]["evidence_sufficient"] is True


def test_report_never_auto_changes_policy():
    report = build_committee_learning_report(observations=full_observations(), completed_decision_traces=30, history_months=6)
    assert report["automatic_policy_change_allowed"] is False
    assert report["human_approval_required"] is True


def test_write_learning_report(tmp_path):
    report = build_committee_learning_report(observations=full_observations(), completed_decision_traces=30, history_months=6)
    output = write_committee_learning_report(report, tmp_path / "results" / "learning.json")
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["plugin_id"] == "SWING-001"


def test_unsafe_report_is_not_written(tmp_path):
    report = build_committee_learning_report()
    report["paper_trade_mode"] = False
    with pytest.raises(ValueError):
        write_committee_learning_report(report, tmp_path / "learning.json")

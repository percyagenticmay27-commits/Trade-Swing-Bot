from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from swing_trade_bot.swing_committee_traceability import (
    BIAS_FIELDS,
    COMMITTEE_SEQUENCE,
    append_unique_outcomes,
    build_committee_step,
    build_decision_trace,
    build_outcome_attachment,
    load_traceability_config,
    validate_decision_trace,
    validate_traceability_config,
    write_decision_trace,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "swing_committee_traceability.json"


@pytest.fixture()
def config() -> dict:
    return load_traceability_config(CONFIG)


def step(committee_id: str, status: str = "PASS", evidence: dict | None = None) -> dict:
    return build_committee_step(
        evaluation_cycle_id="CYCLE-001",
        symbol="AMD",
        strategy_id="STRATEGY_A",
        committee_id=committee_id,
        sequence=COMMITTEE_SEQUENCE.index(committee_id) + 1,
        status=status,
        reason_codes=[f"{committee_id}_{status}"],
        evidence=evidence or {"score": 80.0},
        source_artifacts=["results/evidence.json"],
    )


def approved_steps() -> list[dict]:
    return [
        step("DISCOVERY_COMMITTEE"),
        step("OPPORTUNITY_COMMITTEE", evidence={"opportunity_quality_score": 92.0}),
        step("ENTRY_COMMITTEE", evidence={"entry_score": 84.0}),
        step("PORTFOLIO_COMMITTEE", evidence={"target_allocation_percent": 25.0}),
        step("EXIT_COMMITTEE", "NOT_APPLICABLE", evidence={}),
    ]


def trace(steps: list[dict] | None = None, final_status: str = "ALLOCATED") -> dict:
    return build_decision_trace(
        evaluation_cycle_id="CYCLE-001",
        symbol="AMD",
        strategy_id="STRATEGY_A",
        committee_steps=steps or approved_steps(),
        final_status=final_status,
        source_artifacts=["results/opportunity_quality.json", "results/entry_report.json"],
        bias_audit={field: False for field in BIAS_FIELDS},
        generated_at_utc="2026-07-27T20:00:00Z",
    )


def test_config_loads(config):
    assert config["plugin_id"] == "SWING-001"


def test_config_is_valid(config):
    assert validate_traceability_config(config).valid


def test_committee_sequence_is_frozen(config):
    assert tuple(config["committee_sequence"]) == COMMITTEE_SEQUENCE


@pytest.mark.parametrize("field,bad", [
    ("paper_trade_mode", False),
    ("advisory_only", False),
    ("append_only", False),
    ("automatic_policy_change_allowed", True),
    ("broker_execution_allowed", True),
    ("capital_movement_allowed", True),
])
def test_config_safety_locks(config, field, bad):
    changed = copy.deepcopy(config)
    changed[field] = bad
    assert not validate_traceability_config(changed).valid


def test_config_rejects_changed_committee_order(config):
    changed = copy.deepcopy(config)
    changed["committee_sequence"].reverse()
    assert not validate_traceability_config(changed).valid


def test_config_requires_all_bias_fields(config):
    changed = copy.deepcopy(config)
    changed["bias_audit_fields"].pop()
    assert not validate_traceability_config(changed).valid


def test_build_step_creates_deterministic_id():
    first = step("ENTRY_COMMITTEE")
    second = step("ENTRY_COMMITTEE")
    assert first["step_id"] == second["step_id"]
    assert first["input_snapshot_hash"] == second["input_snapshot_hash"]


def test_step_id_changes_when_evidence_changes():
    first = step("ENTRY_COMMITTEE", evidence={"entry_score": 80.0})
    second = step("ENTRY_COMMITTEE", evidence={"entry_score": 40.0})
    assert first["step_id"] != second["step_id"]


def test_unknown_committee_rejected():
    with pytest.raises(ValueError):
        build_committee_step(
            evaluation_cycle_id="CYCLE-001", symbol="AMD", strategy_id="STRATEGY_A",
            committee_id="UNKNOWN", sequence=1, status="PASS"
        )


def test_wrong_committee_sequence_rejected():
    with pytest.raises(ValueError):
        build_committee_step(
            evaluation_cycle_id="CYCLE-001", symbol="AMD", strategy_id="STRATEGY_A",
            committee_id="ENTRY_COMMITTEE", sequence=2, status="PASS"
        )


def test_unknown_step_status_rejected():
    with pytest.raises(ValueError):
        build_committee_step(
            evaluation_cycle_id="CYCLE-001", symbol="AMD", strategy_id="STRATEGY_A",
            committee_id="ENTRY_COMMITTEE", sequence=3, status="BUY"
        )


def test_valid_approved_trace_passes():
    result = validate_decision_trace(trace())
    assert result.valid


def test_trace_id_is_deterministic():
    assert trace()["decision_trace_id"] == trace()["decision_trace_id"]


def test_trace_id_changes_with_decision_evidence():
    first = trace()
    changed_steps = approved_steps()
    changed_steps[2] = step("ENTRY_COMMITTEE", evidence={"entry_score": 71.0})
    second = trace(changed_steps)
    assert first["decision_trace_id"] != second["decision_trace_id"]


def test_symbol_is_normalized():
    built = build_decision_trace(
        evaluation_cycle_id="CYCLE-001", symbol="amdl", strategy_id="strategy_b",
        committee_steps=approved_steps(), final_status="allocated",
        source_artifacts=["source.json"], bias_audit={field: False for field in BIAS_FIELDS}
    )
    assert built["symbol"] == "AMDL"
    assert built["strategy_id"] == "STRATEGY_B"


def test_entry_veto_skips_portfolio():
    steps = [
        step("DISCOVERY_COMMITTEE"),
        step("OPPORTUNITY_COMMITTEE", evidence={"opportunity_quality_score": 95.0}),
        step("ENTRY_COMMITTEE", "VETO", evidence={"entry_score": 42.0}),
        step("PORTFOLIO_COMMITTEE", "SKIPPED", evidence={}),
        step("EXIT_COMMITTEE", "NOT_APPLICABLE", evidence={}),
    ]
    built = trace(steps, "WAIT")
    assert built["final_status"] == "WAIT"
    assert validate_decision_trace(built).valid


def test_entry_veto_with_allocation_is_rejected():
    steps = [
        step("DISCOVERY_COMMITTEE"),
        step("OPPORTUNITY_COMMITTEE"),
        step("ENTRY_COMMITTEE", "VETO"),
        step("PORTFOLIO_COMMITTEE", "PASS"),
    ]
    raw = trace(approved_steps())
    raw["committee_steps"] = steps
    result = validate_decision_trace(raw)
    assert not result.valid
    assert any("skipped after Entry veto" in error for error in result.errors)


def test_opportunity_rejection_skips_entry_and_portfolio():
    steps = [
        step("DISCOVERY_COMMITTEE"),
        step("OPPORTUNITY_COMMITTEE", "FAIL", evidence={"opportunity_quality_score": 60.0}),
        step("ENTRY_COMMITTEE", "SKIPPED", evidence={}),
        step("PORTFOLIO_COMMITTEE", "SKIPPED", evidence={}),
        step("EXIT_COMMITTEE", "NOT_APPLICABLE", evidence={}),
    ]
    assert validate_decision_trace(trace(steps, "REJECTED")).valid


def test_opportunity_rejection_with_entry_pass_is_rejected():
    raw = trace()
    raw["committee_steps"][1]["status"] = "FAIL"
    result = validate_decision_trace(raw)
    assert not result.valid


def test_duplicate_committee_step_rejected():
    raw = trace()
    raw["committee_steps"].append(copy.deepcopy(raw["committee_steps"][-1]))
    assert not validate_decision_trace(raw).valid


def test_out_of_order_steps_rejected():
    raw = trace()
    raw["committee_steps"][1], raw["committee_steps"][2] = raw["committee_steps"][2], raw["committee_steps"][1]
    assert not validate_decision_trace(raw).valid


@pytest.mark.parametrize("field", BIAS_FIELDS)
def test_every_bias_flag_must_remain_false(field):
    raw = trace()
    raw["bias_audit"][field] = True
    result = validate_decision_trace(raw)
    assert not result.valid
    assert any(field in error for error in result.errors)


def test_missing_source_artifacts_creates_warning():
    raw = trace()
    raw["source_artifacts"] = []
    result = validate_decision_trace(raw)
    assert result.valid
    assert result.warnings


def test_outcome_attachment_is_deterministic():
    kwargs = dict(
        decision_trace_id="SWING-TRACE-ABC",
        measurement_horizon="5_TRADING_DAYS",
        metrics={"return_percent": 4.2, "maximum_adverse_excursion_percent": -1.0},
        source_artifacts=["results/outcome.json"],
        measured_at_utc="2026-08-03T20:00:00Z",
    )
    assert build_outcome_attachment(**kwargs)["record_key"] == build_outcome_attachment(**kwargs)["record_key"]


def test_outcome_does_not_allow_policy_change():
    outcome = build_outcome_attachment(
        decision_trace_id="SWING-TRACE-ABC", measurement_horizon="10_TRADING_DAYS",
        metrics={"return_percent": 8.0}, source_artifacts=["outcome.json"]
    )
    assert outcome["automatic_policy_change_allowed"] is False
    assert outcome["append_only"] is True


def test_append_unique_outcomes_deduplicates():
    outcome = build_outcome_attachment(
        decision_trace_id="SWING-TRACE-ABC", measurement_horizon="3_TRADING_DAYS",
        metrics={"return_percent": 1.0}, source_artifacts=["outcome.json"]
    )
    combined = append_unique_outcomes([outcome], [outcome])
    assert len(combined) == 1


def test_append_unique_outcomes_preserves_existing_order():
    first = build_outcome_attachment(
        decision_trace_id="TRACE-1", measurement_horizon="3_DAYS",
        metrics={"return_percent": 1.0}, source_artifacts=["one.json"]
    )
    second = build_outcome_attachment(
        decision_trace_id="TRACE-1", measurement_horizon="5_DAYS",
        metrics={"return_percent": 2.0}, source_artifacts=["two.json"]
    )
    combined = append_unique_outcomes([first], [second])
    assert [row["outcome_id"] for row in combined] == [first["outcome_id"], second["outcome_id"]]


def test_outcome_without_record_key_rejected():
    with pytest.raises(ValueError):
        append_unique_outcomes([], [{"decision_trace_id": "TRACE"}])


def test_write_trace(trace_path=Path):
    pass


def test_write_decision_trace(tmp_path):
    output = write_decision_trace(trace(), tmp_path / "results" / "trace.json")
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["symbol"] == "AMD"


def test_invalid_trace_is_not_written(tmp_path):
    raw = trace()
    raw["paper_trade_mode"] = False
    with pytest.raises(ValueError):
        write_decision_trace(raw, tmp_path / "trace.json")

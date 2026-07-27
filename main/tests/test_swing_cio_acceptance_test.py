from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from swing_trade_bot.swing_cio_acceptance_test import (
    COMMITTEE_SEQUENCE,
    REQUIRED_STAGES,
    build_cio_acceptance_report,
    load_json,
    replay_decision_trace,
    validate_acceptance_config,
    validate_trace_replay,
    write_acceptance_report,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "swing_cio_acceptance_test.json"


@pytest.fixture()
def config() -> dict:
    return load_json(CONFIG)


@pytest.fixture()
def validation_report() -> dict:
    return {"overall_status": "READY", "governance_health_score": 100.0, "errors": []}


@pytest.fixture()
def service_registration() -> dict:
    return {
        "plugin_id": "SWING-001",
        "paper_compatible": True,
        "governance_required": True,
        "automatic_activation_allowed": False,
    }


@pytest.fixture()
def profiles() -> dict:
    return {"profiles": [{"strategy_id": "STRATEGY_A"}, {"strategy_id": "STRATEGY_B"}]}


@pytest.fixture()
def governance() -> dict:
    return {"committees": [{"committee_id": item} for item in COMMITTEE_SEQUENCE]}


@pytest.fixture()
def learning() -> dict:
    return {
        "automatic_policy_change_allowed": False,
        "human_approval_required": True,
        "append_only": True,
    }


@pytest.fixture()
def trace() -> dict:
    return {
        "decision_trace_id": "SWING-TRACE-001",
        "symbol": "AMD",
        "strategy_id": "STRATEGY_A",
        "final_status": "ALLOCATED",
        "committee_steps": [
            {
                "committee_id": committee,
                "sequence": index,
                "status": "PASS" if committee != "EXIT_COMMITTEE" else "NOT_APPLICABLE",
                "reason_codes": [f"{committee}_OK"],
                "input_snapshot_hash": f"hash-{index}",
            }
            for index, committee in enumerate(COMMITTEE_SEQUENCE, start=1)
        ],
    }


def build_report(config, validation_report, service_registration, profiles, governance, learning, trace):
    return build_cio_acceptance_report(
        acceptance_config=config,
        validation_report=validation_report,
        service_registration=service_registration,
        strategy_profiles=profiles,
        committee_governance=governance,
        committee_learning=learning,
        decision_trace=trace,
        generated_at_utc="2026-07-27T22:00:00Z",
    )


def test_config_loads(config):
    assert config["plugin_id"] == "SWING-001"


def test_config_valid(config):
    assert validate_acceptance_config(config).valid


def test_required_stages_locked(config):
    assert tuple(config["required_acceptance_stages"]) == REQUIRED_STAGES


def test_committee_sequence_locked(config):
    assert tuple(config["required_committee_sequence"]) == COMMITTEE_SEQUENCE


@pytest.mark.parametrize("field,bad", [
    ("paper_trade_mode", False),
    ("advisory_only", False),
    ("automatic_activation_allowed", True),
    ("broker_execution_allowed", True),
    ("capital_movement_allowed", True),
    ("robinhood_execution_allowed", True),
    ("direct_database_writes", True),
])
def test_safety_locks(config, field, bad):
    changed = copy.deepcopy(config)
    changed[field] = bad
    assert not validate_acceptance_config(changed).valid


def test_validation_status_locked(config):
    changed = copy.deepcopy(config)
    changed["required_validation_status"] = "PASS"
    assert not validate_acceptance_config(changed).valid


def test_health_score_locked(config):
    changed = copy.deepcopy(config)
    changed["minimum_governance_health_score"] = 99.0
    assert not validate_acceptance_config(changed).valid


def test_strategy_ids_locked(config):
    changed = copy.deepcopy(config)
    changed["required_strategy_ids"] = ["STRATEGY_A"]
    assert not validate_acceptance_config(changed).valid


def test_replay_preserves_trace(trace):
    replay = replay_decision_trace(trace)
    assert validate_trace_replay(trace, replay).valid


def test_replay_rejects_changed_final_status(trace):
    replay = replay_decision_trace(trace)
    replay["final_status"] = "WAIT"
    assert not validate_trace_replay(trace, replay).valid


def test_replay_rejects_changed_step(trace):
    replay = replay_decision_trace(trace)
    replay["committee_steps"][2]["status"] = "VETO"
    assert not validate_trace_replay(trace, replay).valid


def test_replay_rejects_wrong_order(trace):
    replay = replay_decision_trace(trace)
    replay["committee_steps"][1], replay["committee_steps"][2] = replay["committee_steps"][2], replay["committee_steps"][1]
    assert not validate_trace_replay(trace, replay).valid


def test_replay_requires_steps():
    with pytest.raises(ValueError):
        replay_decision_trace({"committee_steps": "bad"})


def test_ready_report(config, validation_report, service_registration, profiles, governance, learning, trace):
    report = build_report(config, validation_report, service_registration, profiles, governance, learning, trace)
    assert report["final_result"] == "READY_FOR_CIO"
    assert report["passed_stage_count"] == len(REQUIRED_STAGES)
    assert report["errors"] == []


def test_discovery_failure_blocks_acceptance(config, validation_report, service_registration, profiles, governance, learning, trace):
    changed = copy.deepcopy(service_registration)
    changed["plugin_id"] = "BAD"
    assert build_report(config, validation_report, changed, profiles, governance, learning, trace)["final_result"] == "NOT_READY_FOR_CIO"


def test_registration_failure_blocks_acceptance(config, validation_report, service_registration, profiles, governance, learning, trace):
    changed = copy.deepcopy(service_registration)
    changed["paper_compatible"] = False
    assert build_report(config, validation_report, changed, profiles, governance, learning, trace)["final_result"] == "NOT_READY_FOR_CIO"


def test_validation_failure_blocks_acceptance(config, validation_report, service_registration, profiles, governance, learning, trace):
    changed = copy.deepcopy(validation_report)
    changed["overall_status"] = "NOT_READY"
    assert build_report(config, changed, service_registration, profiles, governance, learning, trace)["final_result"] == "NOT_READY_FOR_CIO"


def test_health_failure_blocks_acceptance(config, validation_report, service_registration, profiles, governance, learning, trace):
    changed = copy.deepcopy(validation_report)
    changed["governance_health_score"] = 99.0
    assert build_report(config, changed, service_registration, profiles, governance, learning, trace)["final_result"] == "NOT_READY_FOR_CIO"


def test_governance_order_failure_blocks_acceptance(config, validation_report, service_registration, profiles, governance, learning, trace):
    changed = copy.deepcopy(governance)
    changed["committees"].reverse()
    assert build_report(config, validation_report, service_registration, profiles, changed, learning, trace)["final_result"] == "NOT_READY_FOR_CIO"


def test_learning_auto_change_blocks_acceptance(config, validation_report, service_registration, profiles, governance, learning, trace):
    changed = copy.deepcopy(learning)
    changed["automatic_policy_change_allowed"] = True
    assert build_report(config, validation_report, service_registration, profiles, governance, changed, trace)["final_result"] == "NOT_READY_FOR_CIO"


def test_missing_strategy_blocks_acceptance(config, validation_report, service_registration, profiles, governance, learning, trace):
    changed = {"profiles": [{"strategy_id": "STRATEGY_A"}]}
    assert build_report(config, validation_report, service_registration, changed, governance, learning, trace)["final_result"] == "NOT_READY_FOR_CIO"


def test_write_report(config, validation_report, service_registration, profiles, governance, learning, trace, tmp_path):
    report = build_report(config, validation_report, service_registration, profiles, governance, learning, trace)
    paths = write_acceptance_report(report, tmp_path / "results")
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    assert json.loads(Path(paths["json"]).read_text(encoding="utf-8"))["final_result"] == "READY_FOR_CIO"

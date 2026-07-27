from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from swing_trade_bot.swing_cio_validation_suite import (
    COMMITTEE_SEQUENCE,
    load_json,
    render_markdown,
    validate_repository,
    validate_suite_config,
    write_validation_report,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "swing_cio_validation_suite.json"


@pytest.fixture()
def config() -> dict:
    return load_json(CONFIG_PATH)


def _payloads() -> dict[str, dict]:
    return {
        "plugin_manifest": {"plugin_id": "SWING-001", "safety": {"paper_trade_mode": True, "advisory_only": True, "broker_execution_enabled": False, "capital_movement_enabled": False, "robinhood_execution_enabled": False, "direct_database_writes": False}},
        "output_contract": {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True},
        "schema_registry": {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True},
        "presentation_adapter": {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "direct_database_writes": False},
        "strategy_service_registration": {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "automatic_activation_allowed": False},
        "strategy_capability_profiles": {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "automatic_activation_allowed": False, "profiles": [{"strategy_id": "STRATEGY_A"}, {"strategy_id": "STRATEGY_B"}]},
        "committee_governance": {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "broker_execution_allowed": False, "capital_movement_allowed": False, "committees": [{"committee_id": item} for item in COMMITTEE_SEQUENCE]},
        "committee_traceability": {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "append_only": True, "automatic_policy_change_allowed": False, "broker_execution_allowed": False, "capital_movement_allowed": False, "committee_sequence": list(COMMITTEE_SEQUENCE), "bias_audit_fields": ["sector_bias_applied", "theme_bias_applied", "concentration_limit_applied", "stock_history_bias_applied", "market_regime_veto_applied"]},
        "committee_learning": {"plugin_id": "SWING-001", "paper_trade_mode": True, "advisory_only": True, "append_only": True, "automatic_policy_change_allowed": False, "broker_execution_allowed": False, "capital_movement_allowed": False, "minimum_evidence": {"completed_decision_traces": 30, "history_months": 6, "observations_per_committee": 10}},
    }


def _build_repo(tmp_path: Path, config: dict, changes: dict[str, dict] | None = None) -> Path:
    payloads = _payloads()
    for name, change in (changes or {}).items():
        payloads[name].update(change)
    for name, relative in config["required_components"].items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payloads[name]), encoding="utf-8")
    return tmp_path


def test_config_loads(config):
    assert config["plugin_id"] == "SWING-001"


def test_config_is_valid(config):
    assert validate_suite_config(config).valid


@pytest.mark.parametrize("field,bad", [
    ("paper_trade_mode", False),
    ("advisory_only", False),
    ("read_only", False),
    ("append_only_learning", False),
    ("automatic_policy_change_allowed", True),
    ("broker_execution_allowed", True),
    ("capital_movement_allowed", True),
    ("robinhood_execution_allowed", True),
])
def test_config_safety_locks(config, field, bad):
    changed = copy.deepcopy(config)
    changed[field] = bad
    assert not validate_suite_config(changed).valid


def test_config_rejects_wrong_plugin(config):
    changed = copy.deepcopy(config)
    changed["plugin_id"] = "BAD"
    assert not validate_suite_config(changed).valid


def test_config_rejects_wrong_committee_order(config):
    changed = copy.deepcopy(config)
    changed["committee_sequence"].reverse()
    assert not validate_suite_config(changed).valid


def test_config_rejects_health_weights_not_100(config):
    changed = copy.deepcopy(config)
    changed["health_weights"]["identity"] = 1
    assert not validate_suite_config(changed).valid


def test_valid_repository_is_ready(config, tmp_path):
    report = validate_repository(_build_repo(tmp_path, config), config)
    assert report["overall_status"] == "READY"
    assert report["governance_health_score"] == 100.0
    assert report["governance_health_grade"] == "A+"
    assert not report["errors"]


def test_every_component_passes(config, tmp_path):
    report = validate_repository(_build_repo(tmp_path, config), config)
    assert len(report["components"]) == len(config["required_components"])
    assert all(item["status"] == "PASS" for item in report["components"])


def test_missing_component_fails(config, tmp_path):
    root = _build_repo(tmp_path, config)
    (root / config["required_components"]["output_contract"]).unlink()
    report = validate_repository(root, config)
    assert report["overall_status"] == "NOT_READY"
    assert any("Missing required component" in error for error in report["errors"])


def test_malformed_component_fails(config, tmp_path):
    root = _build_repo(tmp_path, config)
    (root / config["required_components"]["schema_registry"]).write_text("{bad", encoding="utf-8")
    assert validate_repository(root, config)["overall_status"] == "NOT_READY"


def test_cross_file_identity_mismatch_fails(config, tmp_path):
    root = _build_repo(tmp_path, config, {"output_contract": {"plugin_id": "OTHER"}})
    report = validate_repository(root, config)
    assert any("identity must be SWING-001" in error for error in report["errors"])


@pytest.mark.parametrize("field", ["broker_execution_allowed", "capital_movement_allowed", "automatic_policy_change_allowed"])
def test_forbidden_true_safety_field_fails(config, tmp_path, field):
    root = _build_repo(tmp_path, config, {"committee_learning": {field: True}})
    assert validate_repository(root, config)["overall_status"] == "NOT_READY"


def test_paper_trade_false_fails(config, tmp_path):
    root = _build_repo(tmp_path, config, {"committee_governance": {"paper_trade_mode": False}})
    assert validate_repository(root, config)["category_status"]["safety"] == "FAIL"


def test_advisory_only_false_fails(config, tmp_path):
    root = _build_repo(tmp_path, config, {"presentation_adapter": {"advisory_only": False}})
    assert validate_repository(root, config)["overall_status"] == "NOT_READY"


def test_governance_order_mismatch_fails(config, tmp_path):
    payload = _payloads()["committee_governance"]
    payload["committees"].reverse()
    root = _build_repo(tmp_path, config)
    path = root / config["required_components"]["committee_governance"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert validate_repository(root, config)["category_status"]["governance"] == "FAIL"


def test_traceability_order_mismatch_fails(config, tmp_path):
    root = _build_repo(tmp_path, config, {"committee_traceability": {"committee_sequence": list(reversed(COMMITTEE_SEQUENCE))}})
    assert validate_repository(root, config)["category_status"]["traceability"] == "FAIL"


@pytest.mark.parametrize("field", [
    "sector_bias_applied",
    "theme_bias_applied",
    "concentration_limit_applied",
    "stock_history_bias_applied",
    "market_regime_veto_applied",
])
def test_missing_bias_audit_field_fails(config, tmp_path, field):
    fields = [item for item in config["required_bias_audit_false"] if item != field]
    root = _build_repo(tmp_path, config, {"committee_traceability": {"bias_audit_fields": fields}})
    report = validate_repository(root, config)
    assert any(field in error for error in report["errors"])


@pytest.mark.parametrize("field,bad", [
    ("completed_decision_traces", 29),
    ("history_months", 5),
    ("observations_per_committee", 9),
])
def test_learning_minimums_are_frozen(config, tmp_path, field, bad):
    minimums = {"completed_decision_traces": 30, "history_months": 6, "observations_per_committee": 10}
    minimums[field] = bad
    root = _build_repo(tmp_path, config, {"committee_learning": {"minimum_evidence": minimums}})
    assert validate_repository(root, config)["category_status"]["learning"] == "FAIL"


def test_missing_strategy_a_fails(config, tmp_path):
    root = _build_repo(tmp_path, config, {"strategy_capability_profiles": {"profiles": [{"strategy_id": "STRATEGY_B"}]}})
    assert validate_repository(root, config)["overall_status"] == "NOT_READY"


def test_missing_strategy_b_fails(config, tmp_path):
    root = _build_repo(tmp_path, config, {"strategy_capability_profiles": {"profiles": [{"strategy_id": "STRATEGY_A"}]}})
    assert validate_repository(root, config)["overall_status"] == "NOT_READY"


def test_extra_strategy_fails(config, tmp_path):
    profiles = [{"strategy_id": "STRATEGY_A"}, {"strategy_id": "STRATEGY_B"}, {"strategy_id": "STRATEGY_C"}]
    root = _build_repo(tmp_path, config, {"strategy_capability_profiles": {"profiles": profiles}})
    assert validate_repository(root, config)["overall_status"] == "NOT_READY"


def test_markdown_contains_readiness(config, tmp_path):
    report = validate_repository(_build_repo(tmp_path, config), config)
    markdown = render_markdown(report)
    assert "READY" in markdown
    assert "100.0 / 100" in markdown


def test_write_validation_report(config, tmp_path):
    report = validate_repository(_build_repo(tmp_path / "repo", config), config)
    paths = write_validation_report(report, tmp_path / "results")
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()


def test_written_json_is_valid(config, tmp_path):
    report = validate_repository(_build_repo(tmp_path / "repo", config), config)
    paths = write_validation_report(report, tmp_path / "results")
    saved = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert saved["plugin_id"] == "SWING-001"


def test_load_json_rejects_list_root(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_json(path)

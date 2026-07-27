from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from swing_trade_bot.swing_cio_milestone_1_freeze import (
    FROZEN_COMMITTEES,
    REQUIRED_INTERFACES,
    build_freeze_report,
    load_freeze_config,
    validate_freeze_config,
    write_freeze_report,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "swing_cio_milestone_1_freeze.json"


@pytest.fixture()
def config() -> dict:
    return load_freeze_config(CONFIG)


@pytest.fixture()
def validation_report() -> dict:
    return {"overall_status": "READY", "governance_health_score": 100.0}


@pytest.fixture()
def acceptance_report() -> dict:
    return {"overall_status": "READY_FOR_CIO"}


def test_config_loads(config):
    assert config["plugin_id"] == "SWING-001"


def test_config_is_valid(config):
    assert validate_freeze_config(config).valid


def test_exact_frozen_interfaces(config):
    assert set(config["frozen_interfaces"]) == REQUIRED_INTERFACES


def test_committee_order_is_frozen(config):
    assert tuple(config["frozen_committees"]) == FROZEN_COMMITTEES


def test_strategy_ids_are_frozen(config):
    assert set(config["frozen_strategy_ids"]) == {"STRATEGY_A", "STRATEGY_B"}


@pytest.mark.parametrize("field,bad", [
    ("paper_trade_mode", False),
    ("advisory_only", False),
    ("automatic_activation_allowed", True),
    ("automatic_policy_change_allowed", True),
    ("broker_execution_allowed", True),
    ("capital_movement_allowed", True),
    ("direct_database_writes", True),
])
def test_safety_lock_changes_are_rejected(config, field, bad):
    changed = copy.deepcopy(config)
    changed[field] = bad
    assert not validate_freeze_config(changed).valid


def test_wrong_plugin_id_rejected(config):
    changed = copy.deepcopy(config)
    changed["plugin_id"] = "BAD"
    assert not validate_freeze_config(changed).valid


def test_missing_interface_rejected(config):
    changed = copy.deepcopy(config)
    changed["frozen_interfaces"].pop()
    assert not validate_freeze_config(changed).valid


def test_duplicate_interface_rejected(config):
    changed = copy.deepcopy(config)
    changed["frozen_interfaces"].append(changed["frozen_interfaces"][0])
    assert not validate_freeze_config(changed).valid


def test_changed_committee_order_rejected(config):
    changed = copy.deepcopy(config)
    changed["frozen_committees"].reverse()
    assert not validate_freeze_config(changed).valid


def test_missing_strategy_rejected(config):
    changed = copy.deepcopy(config)
    changed["frozen_strategy_ids"] = ["STRATEGY_A"]
    assert not validate_freeze_config(changed).valid


def test_missing_extension_rules_rejected(config):
    changed = copy.deepcopy(config)
    changed["approved_extension_rules"] = []
    assert not validate_freeze_config(changed).valid


def test_ready_reports_create_frozen_status(config, validation_report, acceptance_report):
    report = build_freeze_report(config, validation_report, acceptance_report)
    assert report["freeze_status"] == "FROZEN"
    assert report["errors"] == []


def test_validation_must_be_ready(config, validation_report, acceptance_report):
    validation_report["overall_status"] = "NOT_READY"
    report = build_freeze_report(config, validation_report, acceptance_report)
    assert report["freeze_status"] == "NOT_FROZEN"


def test_health_score_must_be_100(config, validation_report, acceptance_report):
    validation_report["governance_health_score"] = 99.0
    report = build_freeze_report(config, validation_report, acceptance_report)
    assert report["freeze_status"] == "NOT_FROZEN"


def test_acceptance_must_be_ready_for_cio(config, validation_report, acceptance_report):
    acceptance_report["overall_status"] = "NOT_READY_FOR_CIO"
    report = build_freeze_report(config, validation_report, acceptance_report)
    assert report["freeze_status"] == "NOT_FROZEN"


def test_report_preserves_paper_only(config, validation_report, acceptance_report):
    report = build_freeze_report(config, validation_report, acceptance_report)
    assert report["paper_trade_mode"] is True
    assert report["advisory_only"] is True


def test_write_freeze_report(config, validation_report, acceptance_report, tmp_path):
    report = build_freeze_report(config, validation_report, acceptance_report)
    paths = write_freeze_report(report, tmp_path / "results")
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    assert json.loads(Path(paths["json"]).read_text(encoding="utf-8"))["freeze_status"] == "FROZEN"

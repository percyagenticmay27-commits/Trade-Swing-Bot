from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from swing_trade_bot.swing_local_filesystem_integration import (
    REQUIRED_PATH_FIELDS,
    atomic_write_json,
    build_local_filesystem_registration,
    check_artifact_freshness,
    load_integration_config,
    validate_integration_config,
    write_local_filesystem_registration,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "swing_local_filesystem_integration.json"


@pytest.fixture()
def config() -> dict:
    return load_integration_config(CONFIG_PATH)


def test_config_loads(config):
    assert config["plugin_id"] == "SWING-001"


def test_config_is_valid(config):
    assert validate_integration_config(config).valid


def test_local_transport_is_required(config):
    changed = copy.deepcopy(config)
    changed["transport"] = "HTTP"
    assert not validate_integration_config(changed).valid


@pytest.mark.parametrize("field,bad", [
    ("same_server", False),
    ("read_only_consumer", False),
    ("paper_trade_mode", False),
    ("advisory_only", False),
    ("automatic_activation_allowed", True),
    ("broker_execution_allowed", True),
    ("capital_movement_allowed", True),
    ("direct_database_writes", True),
    ("atomic_publish_required", False),
])
def test_safety_and_integration_locks(config, field, bad):
    changed = copy.deepcopy(config)
    changed[field] = bad
    assert not validate_integration_config(changed).valid


@pytest.mark.parametrize("field", REQUIRED_PATH_FIELDS)
def test_required_paths_are_absolute_tradebot_paths(config, field):
    changed = copy.deepcopy(config)
    changed[field] = "relative/path.json"
    assert not validate_integration_config(changed).valid


def test_artifacts_must_reside_under_artifact_root(config):
    changed = copy.deepcopy(config)
    changed["manifest_path"] = "/home/tradebot/other/manifest.json"
    result = validate_integration_config(changed)
    assert not result.valid
    assert any("artifact_root" in error for error in result.errors)


def test_final_paths_cannot_end_in_tmp(config):
    changed = copy.deepcopy(config)
    changed["acceptance_report_path"] += ".tmp"
    assert not validate_integration_config(changed).valid


def test_stale_threshold_must_exceed_warning_threshold(config):
    changed = copy.deepcopy(config)
    changed["freshness"]["stale_after_minutes"] = changed["freshness"]["warning_after_minutes"]
    assert not validate_integration_config(changed).valid


def test_build_registration(config):
    report = build_local_filesystem_registration(config, generated_at_utc="2026-07-27T22:00:00Z")
    assert report["plugin_id"] == "SWING-001"
    assert report["transport"] == "LOCAL_FILESYSTEM"
    assert report["discovery_status"] == "REGISTERED_FOR_LOCAL_DISCOVERY"
    assert report["read_only_consumer"] is True


def test_build_rejects_invalid_config(config):
    changed = copy.deepcopy(config)
    changed["paper_trade_mode"] = False
    with pytest.raises(ValueError):
        build_local_filesystem_registration(changed)


def test_atomic_write_creates_final_file_and_removes_tmp(tmp_path):
    destination = tmp_path / "report.json"
    atomic_write_json({"status": "READY"}, destination)
    assert destination.exists()
    assert not (tmp_path / "report.json.tmp").exists()
    assert json.loads(destination.read_text(encoding="utf-8"))["status"] == "READY"


def test_atomic_write_replaces_existing_file(tmp_path):
    destination = tmp_path / "report.json"
    destination.write_text('{"status":"OLD"}\n', encoding="utf-8")
    atomic_write_json({"status": "NEW"}, destination)
    assert json.loads(destination.read_text(encoding="utf-8"))["status"] == "NEW"


def test_registration_writer_uses_expected_filename(config, tmp_path):
    registration = build_local_filesystem_registration(config)
    output = write_local_filesystem_registration(registration, tmp_path)
    assert output.name == "swing_local_filesystem_registration.json"


def test_freshness_missing(tmp_path):
    result = check_artifact_freshness(tmp_path / "missing.json", now_timestamp=1000, warning_after_minutes=10, stale_after_minutes=20)
    assert result == "MISSING"


def test_freshness_ignores_temporary_files(tmp_path):
    path = tmp_path / "report.json.tmp"
    path.write_text("{}", encoding="utf-8")
    assert check_artifact_freshness(path, now_timestamp=1000, warning_after_minutes=10, stale_after_minutes=20) == "MISSING"


def test_freshness_states(tmp_path):
    path = tmp_path / "report.json"
    path.write_text("{}", encoding="utf-8")
    os.utime(path, (1000, 1000))
    assert check_artifact_freshness(path, now_timestamp=1060, warning_after_minutes=10, stale_after_minutes=20) == "FRESH"
    assert check_artifact_freshness(path, now_timestamp=1660, warning_after_minutes=10, stale_after_minutes=20) == "WARNING"
    assert check_artifact_freshness(path, now_timestamp=2260, warning_after_minutes=10, stale_after_minutes=20) == "STALE"

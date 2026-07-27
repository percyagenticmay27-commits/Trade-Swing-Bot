import copy
import json
from pathlib import Path

import pytest

from swing_trade_bot.swing_strategy_service_registration import (
    build_and_write_strategy_service_registration,
    build_strategy_service_registration,
    is_discoverable_by_cio,
    load_plugin_manifest,
    validate_strategy_service_registration,
    write_strategy_service_registration,
)


@pytest.fixture
def manifest() -> dict:
    return {
        "plugin_id": "SWING-001",
        "plugin_name": "Trade-Swing-Bot",
        "display_name": "Trade Swing Bot",
        "plugin_type": "STRATEGY_PLUGIN",
        "strategy_class": "SWING_TRADING",
        "plugin_version": "1.4",
        "runtime_status": "AVAILABLE",
        "safety": {
            "paper_trade_mode": True,
            "advisory_only": True,
            "reporting_only": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
            "capital_movement_enabled": False,
        },
    }


def test_builds_dividend_cio_compatible_shape(manifest):
    result = build_strategy_service_registration(manifest)
    assert result["strategy_id"] == "SWING-001"
    assert result["plugin_id"] == "SWING-001"
    assert result["service_id"] == "SWING-001"
    assert result["service_type"] == "STRATEGY_PLUGIN"
    assert result["strategy_plugin"] is True


def test_identity_and_version_come_from_manifest(manifest):
    result = build_strategy_service_registration(manifest)
    assert result["display_name"] == "Trade Swing Bot"
    assert result["version"] == "1.4"
    assert result["module_version"] == "1.4"


def test_default_status_is_discoverable(manifest):
    result = build_strategy_service_registration(manifest)
    assert result["status"] == "AVAILABLE"
    assert is_discoverable_by_cio(result)


def test_safety_boundaries_are_locked(manifest):
    result = build_strategy_service_registration(manifest)
    assert result["paper_trade_mode"] is True
    assert result["paper_compatible"] is True
    assert result["advisory_only"] is True
    assert result["reporting_only"] is True
    assert result["live_trading_enabled"] is False
    assert result["broker_execution_enabled"] is False
    assert result["capital_movement_enabled"] is False
    assert result["automatic_activation_allowed"] is False
    assert result["direct_database_writes"] is False


def test_governance_review_is_required(manifest):
    result = build_strategy_service_registration(manifest)
    assert result["governance_review_required"] is True


def test_database_owner_is_cio(manifest):
    result = build_strategy_service_registration(manifest)
    assert result["database_owner"] == "AI_CIO_PLATFORM"


def test_validation_accepts_valid_registration(manifest):
    result = validate_strategy_service_registration(build_strategy_service_registration(manifest))
    assert result.valid
    assert result.errors == ()

@pytest.mark.parametrize("field", ["strategy_id", "plugin_id", "display_name", "version", "manifest_path", "presentation_path"])
def test_required_fields_are_enforced(manifest, field):
    registration = build_strategy_service_registration(manifest)
    registration[field] = ""
    assert not validate_strategy_service_registration(registration).valid


def test_mismatched_ids_are_rejected(manifest):
    registration = build_strategy_service_registration(manifest)
    registration["plugin_id"] = "OTHER"
    assert not validate_strategy_service_registration(registration).valid

@pytest.mark.parametrize("status", ["OFFLINE", "DISABLED", "ERROR"])
def test_ineligible_status_is_rejected(manifest, status):
    registration = build_strategy_service_registration(manifest)
    registration["status"] = status
    assert not validate_strategy_service_registration(registration).valid

@pytest.mark.parametrize("field", ["enabled", "strategy_plugin", "paper_trade_mode", "paper_compatible", "advisory_only", "reporting_only", "governance_review_required"])
def test_required_true_flags_are_enforced(manifest, field):
    registration = build_strategy_service_registration(manifest)
    registration[field] = False
    assert not validate_strategy_service_registration(registration).valid

@pytest.mark.parametrize("field", ["live_trading_enabled", "broker_execution_enabled", "capital_movement_enabled", "automatic_activation_allowed", "direct_database_writes"])
def test_required_false_flags_are_enforced(manifest, field):
    registration = build_strategy_service_registration(manifest)
    registration[field] = True
    assert not validate_strategy_service_registration(registration).valid


def test_invalid_registration_is_not_written(tmp_path, manifest):
    registration = build_strategy_service_registration(manifest)
    registration["paper_trade_mode"] = False
    with pytest.raises(ValueError):
        write_strategy_service_registration(registration, tmp_path / "registration.json")


def test_write_registration_creates_json(tmp_path, manifest):
    registration = build_strategy_service_registration(manifest)
    path = write_strategy_service_registration(registration, tmp_path / "results" / "registration.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["strategy_id"] == "SWING-001"


def test_load_manifest_requires_object(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_plugin_manifest(path)


def test_build_and_write_uses_manifest(tmp_path, manifest):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output_path = tmp_path / "results" / "swing_strategy_service_registration.json"
    result = build_and_write_strategy_service_registration(manifest_path, output_path)
    assert result == output_path
    assert json.loads(result.read_text(encoding="utf-8"))["plugin_id"] == "SWING-001"


def test_source_manifest_is_not_modified(manifest):
    original = copy.deepcopy(manifest)
    build_strategy_service_registration(manifest)
    assert manifest == original

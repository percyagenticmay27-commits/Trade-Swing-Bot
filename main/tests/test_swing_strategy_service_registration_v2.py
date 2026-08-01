import copy
import json
from pathlib import Path, PurePosixPath

import pytest

from swing_trade_bot.swing_strategy_service_registration import (
    CAPABILITIES,
    DASHBOARD_ARTIFACTS,
    DEPLOYMENT_ROOT,
    build_strategy_service_registration,
    validate_strategy_service_registration,
)

CONFIG_PATH = Path("configs/swing_strategy_service_registration.json")
ALLOWED_REPORT_FILENAMES = {
    "opportunity_quality_report.json",
    "executive_dashboard.json",
    "monthly_command_center.json",
    "portfolio_allocations.json",
    "portfolio_risk.json",
    "position_lifecycle.json",
    "watchlist_report.json",
    "stock_performance_report.json",
    "weekly_stock_report.json",
    "market_data_refresh_status.json",
    "swing_daily_cycle_report.json",
}


def load_registration() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def manifest() -> dict:
    return {
        "plugin_id": "SWING-001",
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


def test_registry_v2_metadata_validates():
    registration = load_registration()
    result = validate_strategy_service_registration(registration)
    assert result.valid, result.errors
    assert registration["plugin_contract_version"] == "2.0"


def test_builder_produces_registry_v2_metadata():
    registration = build_strategy_service_registration(manifest())
    assert registration["plugin_contract_version"] == "2.0"
    assert validate_strategy_service_registration(registration).valid


def test_capability_names_are_deterministic_and_unique():
    registration = load_registration()
    capabilities = registration["capabilities"]
    assert capabilities == sorted(capabilities)
    assert len(capabilities) == len(set(capabilities))
    assert tuple(capabilities) == CAPABILITIES


def test_artifact_ids_are_unique():
    artifacts = load_registration()["dashboard_artifacts"]
    artifact_ids = [item["artifact_id"] for item in artifacts]
    assert len(artifact_ids) == len(set(artifact_ids))


def test_artifact_paths_are_absolute_and_rooted_on_digitalocean():
    for artifact in load_registration()["dashboard_artifacts"]:
        path = artifact["path"]
        assert PurePosixPath(path).is_absolute()
        assert path.startswith(DEPLOYMENT_ROOT + "/results/")
        assert artifact["scope"] == "STRATEGY"


def test_only_existing_swing_report_filenames_are_declared():
    declared = {
        PurePosixPath(item["path"]).name
        for item in load_registration()["dashboard_artifacts"]
    }
    assert declared == ALLOWED_REPORT_FILENAMES
    assert declared == {PurePosixPath(item["path"]).name for item in DASHBOARD_ARTIFACTS}


def test_optional_missing_reports_do_not_invalidate_registration(tmp_path):
    registration = load_registration()
    optional = [item for item in registration["dashboard_artifacts"] if item["required"] is False]
    assert optional
    assert all(not (tmp_path / PurePosixPath(item["path"]).name).exists() for item in optional)
    result = validate_strategy_service_registration(registration)
    assert result.valid, result.errors


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("paper_trade_mode", False),
        ("paper_compatible", False),
        ("advisory_only", False),
        ("reporting_only", False),
        ("live_trading_enabled", True),
        ("broker_execution_enabled", True),
        ("capital_movement_enabled", True),
        ("automatic_activation_allowed", True),
        ("governance_review_required", False),
        ("direct_database_writes", True),
    ],
)
def test_unsafe_paper_safety_values_are_rejected(field, unsafe_value):
    registration = load_registration()
    registration[field] = unsafe_value
    assert not validate_strategy_service_registration(registration).valid


def test_duplicate_capability_is_rejected():
    registration = load_registration()
    registration["capabilities"].append(registration["capabilities"][0])
    assert not validate_strategy_service_registration(registration).valid


def test_duplicate_artifact_id_is_rejected():
    registration = load_registration()
    duplicate = copy.deepcopy(registration["dashboard_artifacts"][0])
    registration["dashboard_artifacts"].append(duplicate)
    assert not validate_strategy_service_registration(registration).valid


def test_relative_artifact_path_is_rejected():
    registration = load_registration()
    registration["dashboard_artifacts"][0]["path"] = "results/opportunity_quality_report.json"
    assert not validate_strategy_service_registration(registration).valid


def test_no_trade_dividend_bot_production_imports_exist():
    source = Path("src/swing_trade_bot/swing_strategy_service_registration.py").read_text(
        encoding="utf-8"
    )
    lowered = source.lower()
    assert "trade_dividend_bot" not in lowered
    assert "trade-dividend-bot" not in lowered
    assert "dividend_strategy" not in lowered

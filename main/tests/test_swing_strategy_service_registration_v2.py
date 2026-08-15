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
PUBLISHED_PATH = Path("results/swing_strategy_service_registration.json")
ALLOWED_REPORT_FILENAMES = {
    "opportunity_quality_report.json",
    "executive_dashboard.json",
    "monthly_command_center.json",
    "portfolio_allocations.json",
    "trade_lifecycle_report.json",
    "watchlist_report.json",
    "stock_performance_report.json",
    "weekly_stock_report.json",
    "market_data_refresh_status.json",
    "swing_daily_cycle_report.json",
    "enterprise_strategy_kpis.json",
    "swing_strategy_alerts_report.json",
    "swing_trade_analytics_report.json",
}


def load_registration(path: Path = CONFIG_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest() -> dict:
    return {
        "plugin_id": "SWING-001",
        "display_name": "Trade Swing Bot",
        "plugin_type": "STRATEGY_PLUGIN",
        "strategy_class": "SWING_TRADING",
        "plugin_version": "1.6",
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
    assert registration["repository_root"] == DEPLOYMENT_ROOT


def test_published_registration_matches_configured_registry_v2_metadata():
    assert PUBLISHED_PATH.exists()
    configured = load_registration(CONFIG_PATH)
    published = load_registration(PUBLISHED_PATH)
    assert published == configured
    assert len(published["capabilities"]) == len(CAPABILITIES)
    assert len(published["dashboard_artifacts"]) == len(DASHBOARD_ARTIFACTS)


def test_builder_produces_registry_v2_metadata():
    registration = build_strategy_service_registration(manifest())
    assert registration["plugin_contract_version"] == "2.0"
    assert registration["repository_root"] == DEPLOYMENT_ROOT
    assert validate_strategy_service_registration(registration).valid


def test_capability_names_are_deterministic_unique_and_host_compatible():
    registration = load_registration()
    capabilities = registration["capabilities"]
    artifact_types = [item["artifact_type"].lower() for item in registration["dashboard_artifacts"]]
    assert capabilities == sorted(capabilities)
    assert len(capabilities) == len(set(capabilities))
    assert tuple(capabilities) == CAPABILITIES
    assert set(artifact_types) <= set(capabilities)
    assert all(item == item.lower() for item in capabilities)
    assert "portfolio_risk" not in capabilities


def test_artifact_ids_are_unique():
    artifacts = load_registration()["dashboard_artifacts"]
    artifact_ids = [item["artifact_id"] for item in artifacts]
    assert len(artifact_ids) == len(set(artifact_ids))


def test_evidence_paths_are_repository_relative_and_contained():
    registration = load_registration()
    assert registration["repository_root"] == DEPLOYMENT_ROOT
    for field in ("manifest_path", "presentation_path"):
        path = PurePosixPath(registration[field])
        assert not path.is_absolute()
        assert ".." not in path.parts
    for artifact in registration["dashboard_artifacts"]:
        path = PurePosixPath(artifact["path"])
        assert not path.is_absolute()
        assert path.parts[0] == "results"
        assert ".." not in path.parts
        assert artifact["scope"] == "STRATEGY"


def test_only_authoritative_swing_report_filenames_are_declared():
    declared = {PurePosixPath(item["path"]).name for item in load_registration()["dashboard_artifacts"]}
    assert declared == ALLOWED_REPORT_FILENAMES
    assert declared == {PurePosixPath(item["path"]).name for item in DASHBOARD_ARTIFACTS}


def test_position_lifecycle_uses_authentic_trade_lifecycle_artifact():
    artifact = next(item for item in load_registration()["dashboard_artifacts"] if item["artifact_type"] == "position_lifecycle")
    assert artifact["path"] == "results/trade_lifecycle_report.json"


def test_strategy_kpi_artifact_is_declared_for_dashboard_evidence():
    registration = load_registration()
    artifact = next(item for item in registration["dashboard_artifacts"] if item["artifact_type"] == "strategy_kpis")
    assert artifact["path"] == "results/enterprise_strategy_kpis.json"
    assert artifact["required"] is False
    assert "strategy_kpis" in registration["capabilities"]


def test_all_runtime_report_artifacts_are_optional():
    artifacts = load_registration()["dashboard_artifacts"]
    assert artifacts
    assert all(item["required"] is False for item in artifacts)
    assert all(item["authoritative"] is True for item in artifacts)


def test_optional_missing_reports_do_not_invalidate_registration(tmp_path):
    registration = load_registration()
    assert all(not (tmp_path / PurePosixPath(item["path"]).name).exists() for item in registration["dashboard_artifacts"])
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
        ("order_placement_enabled", True),
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


def test_required_runtime_artifact_is_rejected():
    registration = load_registration()
    registration["dashboard_artifacts"][0]["required"] = True
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


def test_artifact_without_matching_capability_is_rejected():
    registration = load_registration()
    registration["dashboard_artifacts"][0]["artifact_type"] = "unknown_artifact"
    result = validate_strategy_service_registration(registration)
    assert not result.valid
    assert any("no matching enabled capability" in error for error in result.errors)


def test_absolute_artifact_path_is_rejected():
    registration = load_registration()
    registration["dashboard_artifacts"][0]["path"] = f"{DEPLOYMENT_ROOT}/results/opportunity_quality_report.json"
    assert not validate_strategy_service_registration(registration).valid


def test_parent_traversal_artifact_path_is_rejected():
    registration = load_registration()
    registration["dashboard_artifacts"][0]["path"] = "results/../outside.json"
    assert not validate_strategy_service_registration(registration).valid


def test_no_trade_dividend_bot_production_imports_exist():
    source = Path("src/swing_trade_bot/swing_strategy_service_registration.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "trade_dividend_bot" not in lowered
    assert "trade-dividend-bot" not in lowered
    assert "dividend_strategy" not in lowered

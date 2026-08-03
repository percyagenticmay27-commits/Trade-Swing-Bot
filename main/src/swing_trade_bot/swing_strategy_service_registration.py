"""Enterprise Registry v2 export for the paper-only Swing strategy plugin.

This module publishes descriptive registration metadata and read-only evidence
paths. It does not move capital, activate strategies, contact brokers, place
orders, or implement host-side registry behavior.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

MODULE_NAME = "swing_strategy_service_registration"
MODULE_VERSION = "2.1.0"
SCHEMA_VERSION = "1.0"
PLUGIN_CONTRACT_VERSION = "2.0"
DEPLOYMENT_ROOT = "/home/tradebot/Trade-Swing-Bot/main"
DEFAULT_MANIFEST_PATH = f"{DEPLOYMENT_ROOT}/configs/swing_cio_plugin_manifest.json"
DEFAULT_PRESENTATION_PATH = f"{DEPLOYMENT_ROOT}/results/swing_cio_presentation.json"
ELIGIBLE_STATUSES = {"ONLINE", "ENABLED", "AVAILABLE", "HEALTHY", "READY"}

# Enterprise Registry v2 matches normalized artifact_type values to enabled
# capability names. Keep these identifiers lowercase, sorted, and exact.
CAPABILITIES: tuple[str, ...] = (
    "daily_cycle_status",
    "executive_dashboard",
    "market_data_status",
    "monthly_command_center",
    "opportunity_quality",
    "portfolio_allocations",
    "portfolio_risk",
    "position_lifecycle",
    "stock_performance",
    "strategy_kpis",
    "watchlist",
    "weekly_stock_report",
)


def _artifact(artifact_id: str, artifact_type: str, filename: str) -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "path": f"{DEPLOYMENT_ROOT}/results/{filename}",
        "format": "json",
        "scope": "STRATEGY",
        "authoritative": True,
        "required": False,
    }


DASHBOARD_ARTIFACTS: tuple[dict[str, object], ...] = (
    _artifact("daily_cycle_status", "daily_cycle_status", "swing_daily_cycle_report.json"),
    _artifact("executive_dashboard", "executive_dashboard", "executive_dashboard.json"),
    _artifact("market_data_status", "market_data_status", "market_data_refresh_status.json"),
    _artifact("monthly_command_center", "monthly_command_center", "monthly_command_center.json"),
    _artifact("opportunity_quality", "opportunity_quality", "opportunity_quality_report.json"),
    _artifact("portfolio_allocations", "portfolio_allocations", "portfolio_allocations.json"),
    _artifact("portfolio_risk", "portfolio_risk", "portfolio_risk.json"),
    _artifact("position_lifecycle", "position_lifecycle", "position_lifecycle.json"),
    _artifact("stock_performance", "stock_performance", "stock_performance_report.json"),
    _artifact("strategy_kpis", "strategy_kpis", "enterprise_strategy_kpis.json"),
    _artifact("watchlist", "watchlist", "watchlist_report.json"),
    _artifact("weekly_stock_report", "weekly_stock_report", "weekly_stock_report.json"),
)


@dataclass(frozen=True, slots=True)
class RegistrationValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def load_plugin_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Plugin manifest root must be an object")
    return payload


def _copy_artifacts() -> list[dict[str, object]]:
    return [dict(item) for item in DASHBOARD_ARTIFACTS]


def build_strategy_service_registration(
    manifest: Mapping[str, Any],
    *,
    health: str = "HEALTHY",
    enabled: bool = True,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
    presentation_path: str = DEFAULT_PRESENTATION_PATH,
) -> dict[str, Any]:
    """Translate the Swing plugin manifest into an Enterprise Registry v2 record."""
    safety = manifest.get("safety") if isinstance(manifest.get("safety"), Mapping) else {}
    status = str(manifest.get("runtime_status") or "AVAILABLE").upper()
    plugin_id = str(manifest.get("plugin_id") or "").strip()
    display_name = str(manifest.get("display_name") or manifest.get("plugin_name") or plugin_id).strip()
    version = str(manifest.get("plugin_version") or "").strip()
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_contract_version": PLUGIN_CONTRACT_VERSION,
        "strategy_id": plugin_id,
        "plugin_id": plugin_id,
        "service_id": plugin_id,
        "name": display_name,
        "display_name": display_name,
        "service_type": "STRATEGY_PLUGIN",
        "plugin_type": str(manifest.get("plugin_type") or "STRATEGY_PLUGIN"),
        "strategy_class": str(manifest.get("strategy_class") or "SWING_TRADING"),
        "status": status,
        "runtime_status": status,
        "health": str(health).upper(),
        "health_status": str(health).upper(),
        "enabled": bool(enabled),
        "strategy_plugin": True,
        "paper_trade_mode": safety.get("paper_trade_mode") is True,
        "paper_compatible": safety.get("paper_trade_mode") is True,
        "advisory_only": safety.get("advisory_only") is True,
        "reporting_only": safety.get("reporting_only") is True,
        "live_trading_enabled": safety.get("live_trading_enabled") is True,
        "broker_execution_enabled": safety.get("broker_execution_enabled") is True,
        "capital_movement_enabled": safety.get("capital_movement_enabled") is True,
        "version": version,
        "module_version": version,
        "manifest_path": manifest_path,
        "presentation_path": presentation_path,
        "governance_review_required": True,
        "automatic_activation_allowed": False,
        "database_owner": "AI_CIO_PLATFORM",
        "direct_database_writes": False,
        "capabilities": list(CAPABILITIES),
        "dashboard_artifacts": _copy_artifacts(),
    }


def _validate_capabilities(value: object, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append("capabilities must be a non-empty list")
        return
    if any(not isinstance(item, str) or not item for item in value):
        errors.append("capabilities must contain non-empty strings")
        return
    if value != sorted(value):
        errors.append("capabilities must use deterministic sorted order")
    if len(value) != len(set(value)):
        errors.append("capability names must be unique")


def _validate_absolute_swing_path(value: object, field: str, errors: list[str]) -> None:
    path = str(value or "")
    if not PurePosixPath(path).is_absolute():
        errors.append(f"{field} must be an absolute DigitalOcean path")
    elif not path.startswith(DEPLOYMENT_ROOT + "/"):
        errors.append(f"{field} must be rooted under {DEPLOYMENT_ROOT}")


def _validate_artifacts(value: object, capabilities: object, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append("dashboard_artifacts must be a non-empty list")
        return
    capability_set = set(capabilities) if isinstance(capabilities, list) else set()
    ids: list[str] = []
    for index, artifact in enumerate(value):
        if not isinstance(artifact, Mapping):
            errors.append(f"dashboard_artifacts[{index}] must be an object")
            continue
        for field in ("artifact_id", "artifact_type", "path", "format", "scope", "authoritative", "required"):
            if field not in artifact:
                errors.append(f"dashboard_artifacts[{index}] missing {field}")
        artifact_id = str(artifact.get("artifact_id") or "")
        artifact_type = str(artifact.get("artifact_type") or "").strip().lower()
        ids.append(artifact_id)
        if artifact_type not in capability_set:
            errors.append(f"artifact type has no matching enabled capability: {artifact_type}")
        path = str(artifact.get("path") or "")
        if not PurePosixPath(path).is_absolute():
            errors.append(f"artifact path must be absolute: {path}")
        if not path.startswith(DEPLOYMENT_ROOT + "/results/"):
            errors.append(f"artifact path must be under Swing results: {path}")
        if artifact.get("format") != "json":
            errors.append(f"artifact format must be json: {artifact_id}")
        if artifact.get("scope") != "STRATEGY":
            errors.append(f"artifact scope must be STRATEGY: {artifact_id}")
        if artifact.get("authoritative") is not True:
            errors.append(f"artifact authoritative must be true: {artifact_id}")
        if artifact.get("required") is not False:
            errors.append(f"runtime artifact required must be false: {artifact_id}")
    if len(ids) != len(set(ids)):
        errors.append("artifact IDs must be unique")


def validate_strategy_service_registration(registration: Mapping[str, Any]) -> RegistrationValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    required = (
        "schema_version", "plugin_contract_version", "strategy_id", "plugin_id",
        "display_name", "service_type", "status", "health", "enabled",
        "paper_trade_mode", "paper_compatible", "version", "manifest_path",
        "presentation_path", "capabilities", "dashboard_artifacts",
    )
    for field in required:
        if registration.get(field) in (None, ""):
            errors.append(f"Missing required registration field: {field}")
    if registration.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"Unsupported schema_version: {registration.get('schema_version')}")
    if registration.get("plugin_contract_version") != PLUGIN_CONTRACT_VERSION:
        errors.append("plugin_contract_version must be 2.0")
    if registration.get("strategy_id") != registration.get("plugin_id"):
        errors.append("strategy_id and plugin_id must match")
    if registration.get("service_type") != "STRATEGY_PLUGIN":
        errors.append("service_type must be STRATEGY_PLUGIN")
    if str(registration.get("status", "")).upper() not in ELIGIBLE_STATUSES:
        errors.append(f"Status is not CIO-discoverable: {registration.get('status')}")
    for field in ("enabled", "strategy_plugin", "paper_trade_mode", "paper_compatible", "advisory_only", "reporting_only", "governance_review_required"):
        if registration.get(field) is not True:
            errors.append(f"{field} must be true")
    for field in ("live_trading_enabled", "broker_execution_enabled", "capital_movement_enabled", "automatic_activation_allowed", "direct_database_writes"):
        if registration.get(field) is not False:
            errors.append(f"{field} must be false")
    if registration.get("database_owner") != "AI_CIO_PLATFORM":
        errors.append("database_owner must be AI_CIO_PLATFORM")
    _validate_absolute_swing_path(registration.get("manifest_path"), "manifest_path", errors)
    _validate_absolute_swing_path(registration.get("presentation_path"), "presentation_path", errors)
    _validate_capabilities(registration.get("capabilities"), errors)
    _validate_artifacts(registration.get("dashboard_artifacts"), registration.get("capabilities"), errors)
    if str(registration.get("health", "")).upper() not in {"HEALTHY", "READY", "OK", "WARNING", "UNKNOWN"}:
        warnings.append(f"Unrecognized health value: {registration.get('health')}")
    return RegistrationValidationResult(not errors, tuple(errors), tuple(warnings))


def is_discoverable_by_cio(registration: Mapping[str, Any]) -> bool:
    return validate_strategy_service_registration(registration).valid


def write_strategy_service_registration(registration: Mapping[str, Any], output_path: str | Path) -> Path:
    validation = validate_strategy_service_registration(registration)
    if not validation.valid:
        raise ValueError("Invalid strategy service registration: " + "; ".join(validation.errors))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(registration), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_and_write_strategy_service_registration(
    manifest_path: str | Path,
    output_path: str | Path = "results/swing_strategy_service_registration.json",
    *,
    health: str = "HEALTHY",
    enabled: bool = True,
) -> Path:
    manifest = load_plugin_manifest(manifest_path)
    registration = build_strategy_service_registration(manifest, health=health, enabled=enabled)
    return write_strategy_service_registration(registration, output_path)

"""Enterprise registry export for the paper-only Swing strategy plugin.

Builds a service record compatible with the AI CIO strategy discovery workflow
used by the Dividend platform. The module is descriptive only: it does not move
capital, activate strategies, contact brokers, or place orders.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "swing_strategy_service_registration"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
ELIGIBLE_STATUSES = {"ONLINE", "ENABLED", "AVAILABLE", "HEALTHY", "READY"}


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


def build_strategy_service_registration(
    manifest: Mapping[str, Any],
    *,
    health: str = "HEALTHY",
    enabled: bool = True,
    manifest_path: str = "configs/swing_cio_plugin_manifest.json",
    presentation_path: str = "results/swing_cio_presentation.json",
) -> dict[str, Any]:
    """Translate the Swing plugin manifest into an Enterprise registry record."""
    safety = manifest.get("safety") if isinstance(manifest.get("safety"), Mapping) else {}
    status = str(manifest.get("runtime_status") or "AVAILABLE").upper()
    plugin_id = str(manifest.get("plugin_id") or "").strip()
    display_name = str(manifest.get("display_name") or manifest.get("plugin_name") or plugin_id).strip()
    version = str(manifest.get("plugin_version") or "").strip()
    registration = {
        "schema_version": SCHEMA_VERSION,
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
    }
    return registration


def validate_strategy_service_registration(registration: Mapping[str, Any]) -> RegistrationValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    required = (
        "schema_version", "strategy_id", "plugin_id", "display_name", "service_type",
        "status", "health", "enabled", "paper_trade_mode", "paper_compatible",
        "version", "manifest_path", "presentation_path",
    )
    for field in required:
        if registration.get(field) in (None, ""):
            errors.append(f"Missing required registration field: {field}")

    if registration.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"Unsupported schema_version: {registration.get('schema_version')}")
    if registration.get("strategy_id") != registration.get("plugin_id"):
        errors.append("strategy_id and plugin_id must match")
    if registration.get("service_type") != "STRATEGY_PLUGIN":
        errors.append("service_type must be STRATEGY_PLUGIN")
    if str(registration.get("status", "")).upper() not in ELIGIBLE_STATUSES:
        errors.append(f"Status is not CIO-discoverable: {registration.get('status')}")
    if registration.get("enabled") is not True:
        errors.append("enabled must be true")
    if registration.get("strategy_plugin") is not True:
        errors.append("strategy_plugin must be true")
    if registration.get("paper_trade_mode") is not True:
        errors.append("paper_trade_mode must be true")
    if registration.get("paper_compatible") is not True:
        errors.append("paper_compatible must be true")
    if registration.get("advisory_only") is not True:
        errors.append("advisory_only must be true")
    if registration.get("reporting_only") is not True:
        errors.append("reporting_only must be true")
    for field in ("live_trading_enabled", "broker_execution_enabled", "capital_movement_enabled", "automatic_activation_allowed", "direct_database_writes"):
        if registration.get(field) is not False:
            errors.append(f"{field} must be false")
    if registration.get("governance_review_required") is not True:
        errors.append("governance_review_required must be true")
    if registration.get("database_owner") != "AI_CIO_PLATFORM":
        errors.append("database_owner must be AI_CIO_PLATFORM")
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

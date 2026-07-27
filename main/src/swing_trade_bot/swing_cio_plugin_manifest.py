"""Descriptive AI CIO plugin manifest support for the paper-only Swing Bot.

This module validates and summarizes plugin registration metadata. It does not
run Swing engines, alter report payloads, connect to a broker, place orders,
move capital, or write to PostgreSQL.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "swing_cio_plugin_manifest"
MODULE_VERSION = "1.0.0"
MANIFEST_SCHEMA_VERSION = "1.0"
PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
ADVISORY_ONLY = True

REQUIRED_TOP_LEVEL_FIELDS = (
    "manifest_schema_version",
    "plugin_id",
    "plugin_name",
    "display_name",
    "plugin_type",
    "strategy_class",
    "plugin_version",
    "repository_name",
    "repository_role",
    "lifecycle_status",
    "runtime_status",
    "registration_status",
    "capabilities",
    "published_reports",
    "safety",
    "compatibility",
)

IMMUTABLE_SAFETY_VALUES: dict[str, bool] = {
    "paper_trade_mode": True,
    "advisory_only": True,
    "reporting_only": True,
    "live_trading_enabled": False,
    "broker_execution_enabled": False,
    "order_placement_enabled": False,
    "capital_movement_enabled": False,
    "broker_connection_enabled": False,
    "robinhood_execution_enabled": False,
    "investor_controls_live_mode": True,
    "postgres_required": False,
}

ALLOWED_ARTIFACT_SUFFIXES = {".json", ".csv", ".md", ".html", ".zip"}


@dataclass(frozen=True, slots=True)
class ManifestValidationResult:
    """Validation outcome for one Swing CIO plugin manifest."""

    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def load_plugin_manifest(path: str | Path) -> dict[str, Any]:
    """Load a UTF-8 JSON plugin manifest."""

    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Plugin manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Plugin manifest is not valid JSON: {manifest_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Plugin manifest root must be a JSON object")
    return payload


def validate_plugin_manifest(
    manifest: Mapping[str, Any],
    *,
    repository_root: str | Path | None = None,
) -> ManifestValidationResult:
    """Validate descriptive registration metadata without running any engine."""

    errors: list[str] = []
    warnings: list[str] = []

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in manifest:
            errors.append(f"Missing required field: {field}")

    _validate_identity(manifest, errors)
    _validate_capabilities(manifest.get("capabilities"), errors)
    _validate_reports(manifest.get("published_reports"), errors, warnings, repository_root)
    _validate_safety(manifest.get("safety"), errors)
    _validate_compatibility(manifest.get("compatibility"), errors)

    return ManifestValidationResult(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def build_manifest_summary(manifest: Mapping[str, Any]) -> dict[str, object]:
    """Build a CIO-friendly summary from already-computed metadata."""

    capabilities = manifest.get("capabilities", [])
    reports = manifest.get("published_reports", [])
    safety = manifest.get("safety", {})
    return {
        "plugin_id": manifest.get("plugin_id", ""),
        "plugin_name": manifest.get("plugin_name", ""),
        "plugin_version": manifest.get("plugin_version", ""),
        "registration_status": manifest.get("registration_status", ""),
        "runtime_status": manifest.get("runtime_status", ""),
        "capability_count": len(capabilities) if isinstance(capabilities, list) else 0,
        "published_report_count": len(reports) if isinstance(reports, list) else 0,
        "paper_trade_mode": safety.get("paper_trade_mode") if isinstance(safety, Mapping) else None,
        "advisory_only": safety.get("advisory_only") if isinstance(safety, Mapping) else None,
        "live_trading_enabled": safety.get("live_trading_enabled") if isinstance(safety, Mapping) else None,
        "broker_execution_enabled": safety.get("broker_execution_enabled") if isinstance(safety, Mapping) else None,
    }


def _validate_identity(manifest: Mapping[str, Any], errors: list[str]) -> None:
    if manifest.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"manifest_schema_version must be {MANIFEST_SCHEMA_VERSION}")
    if manifest.get("plugin_id") != "SWING-001":
        errors.append("plugin_id must remain SWING-001")
    if manifest.get("plugin_type") != "STRATEGY_PLUGIN":
        errors.append("plugin_type must be STRATEGY_PLUGIN")
    if manifest.get("strategy_class") != "SWING_TRADING":
        errors.append("strategy_class must be SWING_TRADING")
    if manifest.get("repository_name") != "Trade-Swing-Bot":
        errors.append("repository_name must be Trade-Swing-Bot")
    if manifest.get("registration_status") != "CIO_DISCOVERABLE":
        errors.append("registration_status must be CIO_DISCOVERABLE")
    if not str(manifest.get("plugin_version", "")).strip():
        errors.append("plugin_version cannot be empty")


def _validate_capabilities(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append("capabilities must be a non-empty list")
        return
    identifiers: set[str] = set()
    for index, capability in enumerate(value):
        if not isinstance(capability, Mapping):
            errors.append(f"capabilities[{index}] must be an object")
            continue
        capability_id = str(capability.get("capability_id", "")).strip()
        if not capability_id:
            errors.append(f"capabilities[{index}] is missing capability_id")
        elif capability_id in identifiers:
            errors.append(f"Duplicate capability_id: {capability_id}")
        identifiers.add(capability_id)
        if capability.get("advisory_only") is not True:
            errors.append(f"Capability {capability_id or index} must be advisory_only")
        if not str(capability.get("display_name", "")).strip():
            errors.append(f"Capability {capability_id or index} is missing display_name")


def _validate_reports(
    value: Any,
    errors: list[str],
    warnings: list[str],
    repository_root: str | Path | None,
) -> None:
    if not isinstance(value, list) or not value:
        errors.append("published_reports must be a non-empty list")
        return
    identifiers: set[str] = set()
    root = Path(repository_root) if repository_root is not None else None
    for index, report in enumerate(value):
        if not isinstance(report, Mapping):
            errors.append(f"published_reports[{index}] must be an object")
            continue
        report_id = str(report.get("report_id", "")).strip()
        if not report_id:
            errors.append(f"published_reports[{index}] is missing report_id")
        elif report_id in identifiers:
            errors.append(f"Duplicate report_id: {report_id}")
        identifiers.add(report_id)
        if not str(report.get("owner_module", "")).strip():
            errors.append(f"Report {report_id or index} is missing owner_module")
        if not str(report.get("dashboard_destination", "")).strip():
            errors.append(f"Report {report_id or index} is missing dashboard_destination")
        artifacts = report.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"Report {report_id or index} must declare artifacts")
            continue
        for artifact in artifacts:
            artifact_path = Path(str(artifact))
            if artifact_path.suffix.lower() not in ALLOWED_ARTIFACT_SUFFIXES:
                errors.append(f"Unsupported artifact format: {artifact}")
            if root is not None and not (root / artifact_path).exists():
                message = f"Artifact not currently present: {artifact}"
                if report.get("required") is True:
                    errors.append(message)
                else:
                    warnings.append(message)


def _validate_safety(value: Any, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append("safety must be an object")
        return
    for key, expected in IMMUTABLE_SAFETY_VALUES.items():
        if value.get(key) is not expected:
            errors.append(f"Safety flag {key} must be {expected}")


def _validate_compatibility(value: Any, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append("compatibility must be an object")
        return
    if value.get("database_owner") != "AI_CIO_PLATFORM":
        errors.append("database_owner must be AI_CIO_PLATFORM")
    if value.get("direct_database_writes") is not False:
        errors.append("direct_database_writes must be false")
    if value.get("changes_existing_report_schemas") is not False:
        errors.append("changes_existing_report_schemas must be false")
    if value.get("changes_existing_engine_calculations") is not False:
        errors.append("changes_existing_engine_calculations must be false")

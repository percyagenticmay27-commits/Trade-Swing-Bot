"""Strict-versioned schema registry for paper-only Swing CIO artifacts."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "swing_schema_registry"
MODULE_VERSION = "1.0.0"
REGISTRY_SCHEMA_VERSION = "1.0"
VERSION_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
SUPPORTED_FORMATS = {"json", "csv", "markdown", "html", "zip"}
SUPPORTED_STATUSES = {"ACTIVE", "DEPRECATED"}


@dataclass(frozen=True, slots=True)
class SchemaRegistryValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def load_schema_registry(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Schema registry root must be an object")
    return payload


def validate_schema_registry(registry: Mapping[str, Any]) -> SchemaRegistryValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    for field in ("registry_schema_version", "registry_id", "plugin_id", "versioning_policy", "registrations"):
        if not registry.get(field):
            errors.append(f"Missing required registry field: {field}")
    if registry.get("registry_schema_version") != REGISTRY_SCHEMA_VERSION:
        errors.append(f"Unsupported registry_schema_version: {registry.get('registry_schema_version')}")
    if registry.get("versioning_policy") != "STRICT_ARTIFACT_VERSIONING":
        errors.append("versioning_policy must be STRICT_ARTIFACT_VERSIONING")
    if registry.get("paper_trade_mode") is not True:
        errors.append("paper_trade_mode must be true")
    if registry.get("advisory_only") is not True:
        errors.append("advisory_only must be true")
    if registry.get("direct_database_writes") is not False:
        errors.append("direct_database_writes must be false")

    registrations = registry.get("registrations")
    if not isinstance(registrations, list) or not registrations:
        errors.append("registrations must be a non-empty list")
        registrations = []

    keys: set[tuple[str, str]] = set()
    active_by_artifact: dict[str, int] = {}
    for index, registration in enumerate(registrations):
        prefix = f"registrations[{index}]"
        if not isinstance(registration, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("artifact_id", "artifact_version", "schema_version", "format", "owner_module", "dashboard_destination", "status"):
            if registration.get(field) in (None, ""):
                errors.append(f"{prefix} missing required field: {field}")
        artifact_id = str(registration.get("artifact_id", ""))
        artifact_version = str(registration.get("artifact_version", ""))
        key = (artifact_id, artifact_version)
        if key in keys:
            errors.append(f"Duplicate schema registration: {artifact_id}@{artifact_version}")
        keys.add(key)
        for version_field in ("artifact_version", "schema_version"):
            value = registration.get(version_field)
            if not isinstance(value, str) or VERSION_PATTERN.fullmatch(value) is None:
                errors.append(f"Invalid {version_field} for {artifact_id}: {value}")
        artifact_format = registration.get("format")
        if artifact_format not in SUPPORTED_FORMATS:
            errors.append(f"Unsupported format for {artifact_id}: {artifact_format}")
        status = registration.get("status")
        if status not in SUPPORTED_STATUSES:
            errors.append(f"Invalid status for {artifact_id}: {status}")
        if status == "ACTIVE":
            active_by_artifact[artifact_id] = active_by_artifact.get(artifact_id, 0) + 1
        if artifact_format == "json" and registration.get("root_type") not in {"object", "array"}:
            errors.append(f"JSON registration {artifact_id} must define root_type")
        if status == "DEPRECATED" and not registration.get("replacement"):
            warnings.append(f"Deprecated registration {artifact_id}@{artifact_version} has no replacement")

    for artifact_id, count in active_by_artifact.items():
        if count > 1:
            warnings.append(f"Artifact {artifact_id} has multiple ACTIVE versions")
    return SchemaRegistryValidationResult(not errors, tuple(errors), tuple(warnings))


def get_schema_registration(registry: Mapping[str, Any], artifact_id: str, artifact_version: str) -> dict[str, Any]:
    for registration in registry.get("registrations", []):
        if isinstance(registration, Mapping) and registration.get("artifact_id") == artifact_id and registration.get("artifact_version") == artifact_version:
            return dict(registration)
    raise KeyError(f"Unknown artifact schema: {artifact_id}@{artifact_version}")


def list_artifact_versions(registry: Mapping[str, Any], artifact_id: str) -> tuple[str, ...]:
    versions = {
        str(item.get("artifact_version"))
        for item in registry.get("registrations", [])
        if isinstance(item, Mapping) and item.get("artifact_id") == artifact_id
    }
    return tuple(sorted(versions, key=_version_key))


def get_latest_active_registration(registry: Mapping[str, Any], artifact_id: str) -> dict[str, Any]:
    candidates = [
        dict(item)
        for item in registry.get("registrations", [])
        if isinstance(item, Mapping) and item.get("artifact_id") == artifact_id and item.get("status") == "ACTIVE"
    ]
    if not candidates:
        raise KeyError(f"No active schema registration for artifact: {artifact_id}")
    return max(candidates, key=lambda item: _version_key(str(item["artifact_version"])))


def is_schema_compatible(registry: Mapping[str, Any], artifact_id: str, artifact_version: str, schema_version: str) -> bool:
    try:
        registration = get_schema_registration(registry, artifact_id, artifact_version)
    except KeyError:
        return False
    return registration.get("schema_version") == schema_version and registration.get("status") in SUPPORTED_STATUSES


def build_registry_summary(registry: Mapping[str, Any]) -> dict[str, object]:
    registrations = [item for item in registry.get("registrations", []) if isinstance(item, Mapping)]
    artifacts = sorted({str(item.get("artifact_id")) for item in registrations})
    return {
        "registry_id": registry.get("registry_id"),
        "plugin_id": registry.get("plugin_id"),
        "versioning_policy": registry.get("versioning_policy"),
        "registration_count": len(registrations),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "paper_trade_mode": registry.get("paper_trade_mode"),
        "advisory_only": registry.get("advisory_only"),
    }


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))

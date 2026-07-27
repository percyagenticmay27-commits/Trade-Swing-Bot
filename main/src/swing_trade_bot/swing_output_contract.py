"""Strict-versioned output contract for the paper-only Swing CIO plugin."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_NAME = "swing_output_contract"
MODULE_VERSION = "1.0.1"
CONTRACT_SCHEMA_VERSION = "1.0"
VERSION_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
SUPPORTED_FORMATS = {"json", "csv", "markdown", "html", "zip"}


@dataclass(frozen=True, slots=True)
class ContractValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def load_output_contract(path: str | Path) -> dict[str, Any]:
    contract_path = Path(path)
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Output contract root must be an object")
    return payload


def validate_output_contract(contract: Mapping[str, Any]) -> ContractValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    for field in ("contract_schema_version", "contract_id", "plugin_id", "versioning_policy", "artifacts"):
        if not contract.get(field):
            errors.append(f"Missing required contract field: {field}")

    if contract.get("contract_schema_version") != CONTRACT_SCHEMA_VERSION:
        errors.append(f"Unsupported contract_schema_version: {contract.get('contract_schema_version')}")
    if contract.get("versioning_policy") != "STRICT_ARTIFACT_VERSIONING":
        errors.append("versioning_policy must be STRICT_ARTIFACT_VERSIONING")
    if contract.get("paper_trade_mode") is not True:
        errors.append("paper_trade_mode must be true")
    if contract.get("advisory_only") is not True:
        errors.append("advisory_only must be true")
    if contract.get("direct_database_writes") is not False:
        errors.append("direct_database_writes must be false")

    compatibility = contract.get("compatibility_policy")
    if not isinstance(compatibility, Mapping):
        errors.append("compatibility_policy must be an object")
    else:
        required_true = (
            "artifact_versions_are_independent",
            "repository_version_does_not_override_artifact_version",
            "additive_optional_fields_are_backward_compatible",
            "removing_or_renaming_fields_requires_major_version",
            "changing_field_type_requires_major_version",
            "new_required_fields_require_major_version",
        )
        for field in required_true:
            if compatibility.get(field) is not True:
                errors.append(f"compatibility_policy.{field} must be true")

    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
        artifacts = []

    artifact_ids: set[str] = set()
    paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        prefix = f"artifacts[{index}]"
        if not isinstance(artifact, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("artifact_id", "path", "format", "owner_module", "artifact_version", "schema_version", "dashboard_destination", "missing_behavior"):
            if artifact.get(field) in (None, ""):
                errors.append(f"{prefix} missing required field: {field}")

        artifact_id = str(artifact.get("artifact_id", ""))
        path = str(artifact.get("path", ""))
        if artifact_id in artifact_ids:
            errors.append(f"Duplicate artifact_id: {artifact_id}")
        artifact_ids.add(artifact_id)
        if path in paths:
            errors.append(f"Duplicate artifact path: {path}")
        paths.add(path)

        artifact_format = artifact.get("format")
        format_supported = artifact_format in SUPPORTED_FORMATS
        if not format_supported:
            errors.append(f"Unsupported artifact format for {artifact_id}: {artifact_format}")
        if path and format_supported and not _path_matches_format(path, str(artifact_format)):
            errors.append(f"Artifact path extension does not match format for {artifact_id}")

        for version_field in ("artifact_version", "schema_version"):
            value = artifact.get(version_field)
            if not isinstance(value, str) or VERSION_PATTERN.fullmatch(value) is None:
                errors.append(f"Invalid {version_field} for {artifact_id}: {value}")

        if artifact.get("missing_behavior") not in {"WARN", "ERROR"}:
            errors.append(f"Invalid missing_behavior for {artifact_id}")
        if artifact.get("required") is True and artifact.get("missing_behavior") != "ERROR":
            errors.append(f"Required artifact {artifact_id} must use missing_behavior ERROR")
        if artifact.get("required") is False and artifact.get("missing_behavior") == "ERROR":
            warnings.append(f"Optional artifact {artifact_id} uses strict missing behavior")

        _validate_unique_string_list(artifact, "required_fields", prefix, errors)
        _validate_unique_string_list(artifact, "record_required_fields", prefix, errors)
        _validate_unique_string_list(artifact, "columns", prefix, errors)
        _validate_unique_string_list(artifact, "required_sections", prefix, errors)

        if artifact_format == "csv" and not artifact.get("columns"):
            errors.append(f"CSV artifact {artifact_id} must define columns")
        if artifact_format == "json" and artifact.get("root_type") not in {"object", "array"}:
            errors.append(f"JSON artifact {artifact_id} must define root_type")

    return ContractValidationResult(not errors, tuple(errors), tuple(warnings))


def validate_artifact_inventory(contract: Mapping[str, Any], root: str | Path) -> ContractValidationResult:
    structural = validate_output_contract(contract)
    errors = list(structural.errors)
    warnings = list(structural.warnings)
    repository_root = Path(root)
    for artifact in contract.get("artifacts", []):
        if not isinstance(artifact, Mapping):
            continue
        artifact_path = repository_root / str(artifact.get("path", ""))
        if artifact_path.exists():
            continue
        message = f"Missing artifact: {artifact.get('path')}"
        if artifact.get("required") is True:
            errors.append(message)
        else:
            warnings.append(message)
    return ContractValidationResult(not errors, tuple(errors), tuple(warnings))


def build_contract_summary(contract: Mapping[str, Any]) -> dict[str, object]:
    artifacts = [item for item in contract.get("artifacts", []) if isinstance(item, Mapping)]
    versions = {str(item.get("artifact_id")): str(item.get("artifact_version")) for item in artifacts}
    return {
        "contract_id": contract.get("contract_id"),
        "plugin_id": contract.get("plugin_id"),
        "versioning_policy": contract.get("versioning_policy"),
        "artifact_count": len(artifacts),
        "artifact_versions": versions,
        "paper_trade_mode": contract.get("paper_trade_mode"),
        "advisory_only": contract.get("advisory_only"),
    }


def _validate_unique_string_list(source: Mapping[str, Any], field: str, prefix: str, errors: list[str]) -> None:
    value = source.get(field)
    if value is None:
        return
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{prefix}.{field} must be a list of non-empty strings")
        return
    if len(value) != len(set(value)):
        errors.append(f"{prefix}.{field} contains duplicates")


def _path_matches_format(path: str, artifact_format: str) -> bool:
    suffixes = {
        "json": ".json",
        "csv": ".csv",
        "markdown": ".md",
        "html": ".html",
        "zip": ".zip",
    }
    expected_suffix = suffixes.get(artifact_format)
    return expected_suffix is not None and path.lower().endswith(expected_suffix)

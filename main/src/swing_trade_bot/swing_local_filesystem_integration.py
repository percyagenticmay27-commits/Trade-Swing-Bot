"""Local-filesystem registration export for AI CIO discovery of the Swing Bot."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "swing_local_filesystem_integration"
MODULE_VERSION = "1.0.0"
INTEGRATION_SCHEMA_VERSION = "1.0"
PLUGIN_ID = "SWING-001"
TRANSPORT = "LOCAL_FILESYSTEM"
REQUIRED_PATH_FIELDS = (
    "plugin_root",
    "artifact_root",
    "manifest_path",
    "output_contract_path",
    "schema_registry_path",
    "acceptance_report_path",
)


@dataclass(frozen=True, slots=True)
class IntegrationValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_integration_config(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Integration configuration root must be an object")
    return payload


def validate_integration_config(payload: Mapping[str, Any]) -> IntegrationValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("integration_schema_version") != INTEGRATION_SCHEMA_VERSION:
        errors.append("integration_schema_version must be 1.0")
    if payload.get("plugin_id") != PLUGIN_ID:
        errors.append("plugin_id must be SWING-001")
    if payload.get("transport") != TRANSPORT:
        errors.append("transport must be LOCAL_FILESYSTEM")
    expected = {
        "same_server": True,
        "read_only_consumer": True,
        "paper_trade_mode": True,
        "advisory_only": True,
        "automatic_activation_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
        "direct_database_writes": False,
        "atomic_publish_required": True,
    }
    for field, value in expected.items():
        if payload.get(field) is not value:
            errors.append(f"{field} must be {str(value).lower()}")
    for field in REQUIRED_PATH_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.startswith("/home/tradebot/"):
            errors.append(f"{field} must be an absolute /home/tradebot path")
    artifact_root = str(payload.get("artifact_root") or "")
    for field in REQUIRED_PATH_FIELDS[2:]:
        value = str(payload.get(field) or "")
        if value and artifact_root and not value.startswith(artifact_root + "/"):
            errors.append(f"{field} must reside under artifact_root")
        if value.endswith(".tmp"):
            errors.append(f"{field} must reference a final artifact, not a temporary file")
    freshness = payload.get("freshness")
    if not isinstance(freshness, Mapping):
        errors.append("freshness must be an object")
    else:
        warning_minutes = freshness.get("warning_after_minutes")
        stale_minutes = freshness.get("stale_after_minutes")
        if not isinstance(warning_minutes, int) or warning_minutes <= 0:
            errors.append("freshness.warning_after_minutes must be a positive integer")
        if not isinstance(stale_minutes, int) or stale_minutes <= 0:
            errors.append("freshness.stale_after_minutes must be a positive integer")
        if isinstance(warning_minutes, int) and isinstance(stale_minutes, int) and stale_minutes <= warning_minutes:
            errors.append("freshness.stale_after_minutes must exceed warning_after_minutes")
    return IntegrationValidationResult(not errors, tuple(errors), tuple(warnings))


def build_local_filesystem_registration(config: Mapping[str, Any], generated_at_utc: str | None = None) -> dict[str, Any]:
    validation = validate_integration_config(config)
    if not validation.valid:
        raise ValueError("Invalid local filesystem integration: " + "; ".join(validation.errors))
    return {
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "integration_schema_version": INTEGRATION_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "plugin_id": PLUGIN_ID,
        "plugin_name": config["plugin_name"],
        "plugin_type": config["plugin_type"],
        "plugin_root": config["plugin_root"],
        "artifact_root": config["artifact_root"],
        "manifest_path": config["manifest_path"],
        "output_contract_path": config["output_contract_path"],
        "schema_registry_path": config["schema_registry_path"],
        "acceptance_report_path": config["acceptance_report_path"],
        "strategy_registration_path": config.get("strategy_registration_path"),
        "capability_profiles_path": config.get("capability_profiles_path"),
        "committee_governance_path": config.get("committee_governance_path"),
        "transport": TRANSPORT,
        "consumer": "AI_CIO",
        "same_server": True,
        "read_only_consumer": True,
        "paper_trade_mode": True,
        "advisory_only": True,
        "automatic_activation_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
        "direct_database_writes": False,
        "atomic_publish_required": True,
        "temporary_suffix": config.get("temporary_suffix", ".tmp"),
        "freshness": dict(config["freshness"]),
        "discovery_status": "REGISTERED_FOR_LOCAL_DISCOVERY",
    }


def atomic_write_json(payload: Mapping[str, Any], destination: str | Path) -> Path:
    """Write JSON to a sibling temporary file, fsync it, then atomically replace final output."""
    final_path = Path(destination)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = final_path.with_name(final_path.name + ".tmp")
    encoded = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    json.loads(temp_path.read_text(encoding="utf-8"))
    os.replace(temp_path, final_path)
    return final_path


def write_local_filesystem_registration(registration: Mapping[str, Any], output_dir: str | Path) -> Path:
    return atomic_write_json(registration, Path(output_dir) / "swing_local_filesystem_registration.json")


def check_artifact_freshness(path: str | Path, *, now_timestamp: float, warning_after_minutes: int, stale_after_minutes: int) -> str:
    artifact = Path(path)
    if not artifact.exists() or artifact.suffix == ".tmp":
        return "MISSING"
    age_minutes = max(0.0, (now_timestamp - artifact.stat().st_mtime) / 60.0)
    if age_minutes >= stale_after_minutes:
        return "STALE"
    if age_minutes >= warning_after_minutes:
        return "WARNING"
    return "FRESH"

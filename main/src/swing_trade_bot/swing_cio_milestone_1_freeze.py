"""Milestone 1 freeze validator for the paper-only Swing CIO contract."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "swing_cio_milestone_1_freeze"
MODULE_VERSION = "1.0.0"
FREEZE_SCHEMA_VERSION = "1.0"
PLUGIN_ID = "SWING-001"
FROZEN_COMMITTEES = (
    "DISCOVERY_COMMITTEE",
    "OPPORTUNITY_COMMITTEE",
    "ENTRY_COMMITTEE",
    "PORTFOLIO_COMMITTEE",
    "EXIT_COMMITTEE",
)
FROZEN_STRATEGIES = {"STRATEGY_A", "STRATEGY_B"}
REQUIRED_INTERFACES = {
    "PLUGIN_MANIFEST",
    "OUTPUT_CONTRACT",
    "SCHEMA_REGISTRY",
    "PRESENTATION_ADAPTER",
    "STRATEGY_SERVICE_REGISTRATION",
    "STRATEGY_CAPABILITY_PROFILES",
    "COMMITTEE_GOVERNANCE",
    "COMMITTEE_TRACEABILITY",
    "COMMITTEE_LEARNING",
    "CIO_VALIDATION_SUITE",
    "CIO_ACCEPTANCE_TEST",
}


@dataclass(frozen=True, slots=True)
class FreezeValidationResult:
    valid: bool
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors)}


def load_freeze_config(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Freeze configuration root must be an object")
    return payload


def validate_freeze_config(payload: Mapping[str, Any]) -> FreezeValidationResult:
    errors: list[str] = []
    if payload.get("freeze_schema_version") != FREEZE_SCHEMA_VERSION:
        errors.append("freeze_schema_version must be 1.0")
    if payload.get("plugin_id") != PLUGIN_ID:
        errors.append("plugin_id must be SWING-001")
    if payload.get("milestone") != "CIO_COMPATIBILITY_MILESTONE_1":
        errors.append("milestone must be CIO_COMPATIBILITY_MILESTONE_1")

    for field, expected in {
        "paper_trade_mode": True,
        "advisory_only": True,
        "automatic_activation_allowed": False,
        "automatic_policy_change_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
        "direct_database_writes": False,
    }.items():
        if payload.get(field) is not expected:
            errors.append(f"{field} must be {str(expected).lower()}")

    interfaces = payload.get("frozen_interfaces")
    if not isinstance(interfaces, list) or set(interfaces) != REQUIRED_INTERFACES:
        errors.append("frozen_interfaces must exactly match the Milestone 1 interface set")
    if len(interfaces or []) != len(set(interfaces or [])):
        errors.append("frozen_interfaces must not contain duplicates")

    committees = tuple(payload.get("frozen_committees") or ())
    if committees != FROZEN_COMMITTEES:
        errors.append("frozen_committees must match the five-committee order")

    strategies = payload.get("frozen_strategy_ids")
    if not isinstance(strategies, list) or set(strategies) != FROZEN_STRATEGIES:
        errors.append("frozen_strategy_ids must contain Strategy A and Strategy B")

    rules = payload.get("approved_extension_rules")
    if not isinstance(rules, list) or not rules:
        errors.append("approved_extension_rules must be a non-empty list")

    return FreezeValidationResult(not errors, tuple(errors))


def build_freeze_report(
    freeze_config: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    acceptance_report: Mapping[str, Any],
) -> dict[str, Any]:
    result = validate_freeze_config(freeze_config)
    errors = list(result.errors)

    if validation_report.get("overall_status") != "READY":
        errors.append("Phase 9F validation report must be READY")
    if float(validation_report.get("governance_health_score", 0.0)) != 100.0:
        errors.append("Phase 9F governance health score must equal 100")
    if acceptance_report.get("overall_status") != "READY_FOR_CIO":
        errors.append("Phase 9F.1 acceptance report must be READY_FOR_CIO")

    status = "FROZEN" if not errors else "NOT_FROZEN"
    return {
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "freeze_schema_version": FREEZE_SCHEMA_VERSION,
        "plugin_id": PLUGIN_ID,
        "milestone": "CIO_COMPATIBILITY_MILESTONE_1",
        "freeze_status": status,
        "paper_trade_mode": True,
        "advisory_only": True,
        "frozen_interfaces": list(freeze_config.get("frozen_interfaces") or []),
        "frozen_committees": list(FROZEN_COMMITTEES),
        "frozen_strategy_ids": sorted(FROZEN_STRATEGIES),
        "approved_extension_rules": list(freeze_config.get("approved_extension_rules") or []),
        "errors": errors,
    }


def render_freeze_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Swing CIO Compatibility Milestone 1 Freeze",
        "",
        f"- Freeze status: **{report.get('freeze_status')}**",
        f"- Plugin ID: `{report.get('plugin_id')}`",
        "- Paper only: **True**",
        "- Advisory only: **True**",
        "",
        "## Frozen Interfaces",
        "",
    ]
    lines.extend(f"- {item}" for item in report.get("frozen_interfaces") or [])
    lines.extend(["", "## Errors", ""])
    errors = report.get("errors") or []
    lines.extend(f"- {error}" for error in errors) if errors else lines.append("- None")
    lines.extend(["", "Any breaking change requires a new governed interface version.", ""])
    return "\n".join(lines)


def write_freeze_report(report: Mapping[str, Any], output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "swing_cio_milestone_1_freeze.json"
    md_path = output / "swing_cio_milestone_1_freeze.md"
    json_path.write_text(json.dumps(dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_freeze_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}

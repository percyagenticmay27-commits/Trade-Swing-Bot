"""Full paper-only CIO validation suite for the Trade Swing Bot."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "swing_cio_validation_suite"
MODULE_VERSION = "1.0.0"
VALIDATION_SCHEMA_VERSION = "1.0"
PLUGIN_ID = "SWING-001"
COMMITTEE_SEQUENCE = (
    "DISCOVERY_COMMITTEE",
    "OPPORTUNITY_COMMITTEE",
    "ENTRY_COMMITTEE",
    "PORTFOLIO_COMMITTEE",
    "EXIT_COMMITTEE",
)


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def validate_suite_config(payload: Mapping[str, Any]) -> ValidationResult:
    errors: list[str] = []
    if payload.get("validation_schema_version") != VALIDATION_SCHEMA_VERSION:
        errors.append("validation_schema_version must be 1.0")
    if payload.get("plugin_id") != PLUGIN_ID:
        errors.append("plugin_id must be SWING-001")
    safety = {
        "paper_trade_mode": True,
        "advisory_only": True,
        "read_only": True,
        "append_only_learning": True,
        "automatic_policy_change_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
        "robinhood_execution_allowed": False,
    }
    for field, expected in safety.items():
        if payload.get(field) is not expected:
            errors.append(f"{field} must be {str(expected).lower()}")
    components = payload.get("required_components")
    if not isinstance(components, Mapping) or not components:
        errors.append("required_components must be a non-empty object")
    if tuple(payload.get("committee_sequence") or ()) != COMMITTEE_SEQUENCE:
        errors.append("committee_sequence must match the frozen order")
    weights = payload.get("health_weights")
    if not isinstance(weights, Mapping) or sum(weights.values()) != 100:
        errors.append("health_weights must total 100")
    return ValidationResult(not errors, tuple(errors), ())


def _find_plugin_id(payload: Mapping[str, Any]) -> Any:
    for key in ("plugin_id", "service_id", "strategy_service_id"):
        if key in payload:
            return payload.get(key)
    return None


def _safety_errors(name: str, payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    nested = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    combined = {**nested, **payload}
    true_fields = ("paper_trade_mode", "advisory_only")
    false_fields = (
        "broker_execution_allowed", "broker_execution_enabled",
        "capital_movement_allowed", "capital_movement_enabled",
        "robinhood_execution_allowed", "robinhood_execution_enabled",
        "automatic_policy_change_allowed", "automatic_activation_allowed",
        "direct_database_writes",
    )
    for field in true_fields:
        if field in combined and combined.get(field) is not True:
            errors.append(f"{name}.{field} must be true")
    for field in false_fields:
        if field in combined and combined.get(field) is not False:
            errors.append(f"{name}.{field} must be false")
    return errors


def validate_repository(root: str | Path, suite_config: Mapping[str, Any]) -> dict[str, Any]:
    root_path = Path(root)
    config_result = validate_suite_config(suite_config)
    errors = list(config_result.errors)
    warnings: list[str] = []
    component_results: list[dict[str, Any]] = []
    loaded: dict[str, dict[str, Any]] = {}

    for name, relative in (suite_config.get("required_components") or {}).items():
        path = root_path / str(relative)
        if not path.exists():
            errors.append(f"Missing required component: {relative}")
            component_results.append({"component": name, "status": "FAIL", "path": str(relative)})
            continue
        try:
            payload = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid component {name}: {exc}")
            component_results.append({"component": name, "status": "FAIL", "path": str(relative)})
            continue
        loaded[name] = payload
        local_errors = _safety_errors(name, payload)
        identity = _find_plugin_id(payload)
        if identity is not None and identity != PLUGIN_ID:
            local_errors.append(f"{name} identity must be SWING-001")
        errors.extend(local_errors)
        component_results.append({
            "component": name,
            "status": "PASS" if not local_errors else "FAIL",
            "path": str(relative),
        })

    governance = loaded.get("committee_governance", {})
    committees = governance.get("committees") if isinstance(governance, Mapping) else None
    if isinstance(committees, list):
        actual = tuple(row.get("committee_id") for row in committees if isinstance(row, Mapping))
        if actual != COMMITTEE_SEQUENCE:
            errors.append("committee_governance order does not match frozen sequence")
    else:
        errors.append("committee_governance must define committees")

    traceability = loaded.get("committee_traceability", {})
    if tuple(traceability.get("committee_sequence") or ()) != COMMITTEE_SEQUENCE:
        errors.append("committee_traceability sequence mismatch")
    for field in suite_config.get("required_bias_audit_false") or []:
        configured = traceability.get("bias_audit_fields") or []
        if field not in configured:
            errors.append(f"committee_traceability missing bias audit field: {field}")

    learning = loaded.get("committee_learning", {})
    minimums = learning.get("minimum_evidence") if isinstance(learning, Mapping) else None
    expected_minimums = {
        "completed_decision_traces": 30,
        "history_months": 6,
        "observations_per_committee": 10,
    }
    if not isinstance(minimums, Mapping):
        errors.append("committee_learning minimum_evidence is missing")
    else:
        for field, expected in expected_minimums.items():
            if minimums.get(field) != expected:
                errors.append(f"committee_learning minimum_evidence.{field} must be {expected}")

    profiles = loaded.get("strategy_capability_profiles", {})
    strategy_ids = {
        row.get("strategy_id") for row in profiles.get("profiles", []) if isinstance(row, Mapping)
    }
    if strategy_ids != {"STRATEGY_A", "STRATEGY_B"}:
        errors.append("strategy capability profiles must contain Strategy A and Strategy B")

    category_status = {
        "identity": not any("identity" in error or "plugin_id" in error for error in errors),
        "components": all(row["status"] == "PASS" for row in component_results),
        "governance": not any("governance" in error or "committee_" in error and "learning" not in error and "traceability" not in error for error in errors),
        "traceability": not any("traceability" in error for error in errors),
        "learning": not any("learning" in error for error in errors),
        "safety": not any("must be true" in error or "must be false" in error for error in errors),
    }
    weights = suite_config.get("health_weights") or {}
    health_score = round(sum(float(weights.get(key, 0)) for key, passed in category_status.items() if passed), 2)
    grade = "A+" if health_score >= 97 else "A" if health_score >= 93 else "B" if health_score >= 80 else "C" if health_score >= 70 else "F"
    overall = "READY" if not errors else "NOT_READY"

    return {
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "validation_schema_version": VALIDATION_SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "plugin_id": PLUGIN_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "overall_status": overall,
        "governance_health_score": health_score,
        "governance_health_grade": grade,
        "category_status": {key: "PASS" if value else "FAIL" for key, value in category_status.items()},
        "components": component_results,
        "errors": errors,
        "warnings": warnings,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Swing CIO Validation Report", "",
        f"- Overall status: **{report.get('overall_status')}**",
        f"- Governance health: **{report.get('governance_health_score')} / 100**",
        f"- Grade: **{report.get('governance_health_grade')}**", "",
        "## Categories", "",
    ]
    for name, status in (report.get("category_status") or {}).items():
        lines.append(f"- {name.replace('_', ' ').title()}: **{status}**")
    lines.extend(["", "## Components", ""])
    for item in report.get("components") or []:
        lines.append(f"- {item.get('component')}: **{item.get('status')}** — `{item.get('path')}`")
    lines.extend(["", "## Errors", ""])
    errors = report.get("errors") or []
    lines.extend(f"- {error}" for error in errors) if errors else lines.append("- None")
    lines.extend(["", "Paper-only, advisory-only validation. No brokerage execution or capital movement is performed.", ""])
    return "\n".join(lines)


def write_validation_report(report: Mapping[str, Any], output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "swing_cio_validation_report.json"
    md_path = output / "swing_cio_validation_report.md"
    json_path.write_text(json.dumps(dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}

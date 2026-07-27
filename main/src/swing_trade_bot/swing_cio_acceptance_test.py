"""End-to-end, paper-only CIO acceptance test for the Trade Swing Bot."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_NAME = "swing_cio_acceptance_test"
MODULE_VERSION = "1.0.0"
ACCEPTANCE_SCHEMA_VERSION = "1.0"
PLUGIN_ID = "SWING-001"
COMMITTEE_SEQUENCE = (
    "DISCOVERY_COMMITTEE",
    "OPPORTUNITY_COMMITTEE",
    "ENTRY_COMMITTEE",
    "PORTFOLIO_COMMITTEE",
    "EXIT_COMMITTEE",
)
REQUIRED_STAGES = (
    "ENTERPRISE_DISCOVERY",
    "PLUGIN_REGISTRATION",
    "FULL_VALIDATION",
    "COMMITTEE_GOVERNANCE",
    "DECISION_TRACE_REPLAY",
    "LEARNING_GOVERNANCE",
    "SAFETY_BOUNDARY",
)


@dataclass(frozen=True, slots=True)
class AcceptanceValidationResult:
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
        raise ValueError("JSON root must be an object")
    return payload


def validate_acceptance_config(payload: Mapping[str, Any]) -> AcceptanceValidationResult:
    errors: list[str] = []
    if payload.get("acceptance_schema_version") != ACCEPTANCE_SCHEMA_VERSION:
        errors.append("acceptance_schema_version must be 1.0")
    if payload.get("plugin_id") != PLUGIN_ID:
        errors.append("plugin_id must be SWING-001")
    expected = {
        "paper_trade_mode": True,
        "advisory_only": True,
        "automatic_activation_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
        "robinhood_execution_allowed": False,
        "direct_database_writes": False,
    }
    for field, value in expected.items():
        if payload.get(field) is not value:
            errors.append(f"{field} must be {str(value).lower()}")
    if tuple(payload.get("required_committee_sequence") or ()) != COMMITTEE_SEQUENCE:
        errors.append("required_committee_sequence must match the frozen order")
    if tuple(payload.get("required_acceptance_stages") or ()) != REQUIRED_STAGES:
        errors.append("required_acceptance_stages must match the frozen sequence")
    if set(payload.get("required_strategy_ids") or ()) != {"STRATEGY_A", "STRATEGY_B"}:
        errors.append("required_strategy_ids must contain Strategy A and Strategy B")
    if payload.get("required_validation_status") != "READY":
        errors.append("required_validation_status must be READY")
    if float(payload.get("minimum_governance_health_score", 0.0)) != 100.0:
        errors.append("minimum_governance_health_score must be 100.0")
    return AcceptanceValidationResult(not errors, tuple(errors), ())


def replay_decision_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    steps = trace.get("committee_steps")
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes, bytearray)):
        raise ValueError("committee_steps must be a sequence")
    replayed = []
    for item in steps:
        if not isinstance(item, Mapping):
            raise ValueError("committee step must be an object")
        replayed.append({
            "committee_id": item.get("committee_id"),
            "sequence": item.get("sequence"),
            "status": item.get("status"),
            "reason_codes": list(item.get("reason_codes") or []),
            "input_snapshot_hash": item.get("input_snapshot_hash"),
        })
    return {
        "decision_trace_id": trace.get("decision_trace_id"),
        "symbol": trace.get("symbol"),
        "strategy_id": trace.get("strategy_id"),
        "final_status": trace.get("final_status"),
        "committee_steps": replayed,
    }


def validate_trace_replay(trace: Mapping[str, Any], replay: Mapping[str, Any]) -> AcceptanceValidationResult:
    errors: list[str] = []
    for field in ("decision_trace_id", "symbol", "strategy_id", "final_status"):
        if trace.get(field) != replay.get(field):
            errors.append(f"Trace replay mismatch: {field}")
    original_steps = trace.get("committee_steps") or []
    replay_steps = replay.get("committee_steps") or []
    if len(original_steps) != len(replay_steps):
        errors.append("Trace replay step count mismatch")
    else:
        for index, (original, copied) in enumerate(zip(original_steps, replay_steps)):
            if not isinstance(original, Mapping) or not isinstance(copied, Mapping):
                errors.append(f"Trace replay invalid step at index {index}")
                continue
            for field in ("committee_id", "sequence", "status", "reason_codes", "input_snapshot_hash"):
                original_value = list(original.get(field) or []) if field == "reason_codes" else original.get(field)
                if original_value != copied.get(field):
                    errors.append(f"Trace replay mismatch at step {index}: {field}")
    actual_order = tuple(
        step.get("committee_id") for step in replay_steps if isinstance(step, Mapping)
    )
    if actual_order != COMMITTEE_SEQUENCE[: len(actual_order)]:
        errors.append("Trace replay committee order mismatch")
    return AcceptanceValidationResult(not errors, tuple(errors), ())


def build_cio_acceptance_report(
    *,
    acceptance_config: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    service_registration: Mapping[str, Any],
    strategy_profiles: Mapping[str, Any],
    committee_governance: Mapping[str, Any],
    committee_learning: Mapping[str, Any],
    decision_trace: Mapping[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    errors = list(validate_acceptance_config(acceptance_config).errors)
    stages: list[dict[str, str]] = []

    def stage(name: str, passed: bool, message: str) -> None:
        stages.append({"stage": name, "status": "PASS" if passed else "FAIL", "message": message})
        if not passed:
            errors.append(f"{name}: {message}")

    service_identity = service_registration.get("plugin_id") or service_registration.get("service_id") or service_registration.get("strategy_service_id")
    stage("ENTERPRISE_DISCOVERY", service_identity == PLUGIN_ID, "Swing strategy is discoverable as SWING-001")

    registration_ready = (
        service_registration.get("paper_compatible") is True
        and service_registration.get("governance_required") is True
        and service_registration.get("automatic_activation_allowed") is False
    )
    stage("PLUGIN_REGISTRATION", registration_ready, "Registration is paper-compatible and governance-controlled")

    validation_ready = (
        validation_report.get("overall_status") == acceptance_config.get("required_validation_status")
        and float(validation_report.get("governance_health_score", 0.0)) >= float(acceptance_config.get("minimum_governance_health_score", 100.0))
        and not validation_report.get("errors")
    )
    stage("FULL_VALIDATION", validation_ready, "Phase 9F reports READY with governance health 100")

    committees = committee_governance.get("committees") or []
    committee_order = tuple(row.get("committee_id") for row in committees if isinstance(row, Mapping))
    stage("COMMITTEE_GOVERNANCE", committee_order == COMMITTEE_SEQUENCE, "Frozen five-committee governance order is intact")

    replay = replay_decision_trace(decision_trace)
    replay_result = validate_trace_replay(decision_trace, replay)
    stage("DECISION_TRACE_REPLAY", replay_result.valid, "Decision trace reproduces the original committee path")
    errors.extend(replay_result.errors)

    profiles = {row.get("strategy_id") for row in strategy_profiles.get("profiles", []) if isinstance(row, Mapping)}
    learning_safe = (
        profiles == {"STRATEGY_A", "STRATEGY_B"}
        and committee_learning.get("automatic_policy_change_allowed") is False
        and committee_learning.get("human_approval_required") is True
        and committee_learning.get("append_only") is True
    )
    stage("LEARNING_GOVERNANCE", learning_safe, "Learning remains append-only, advisory, and human-approved")

    safety_safe = all((
        acceptance_config.get("paper_trade_mode") is True,
        acceptance_config.get("advisory_only") is True,
        acceptance_config.get("broker_execution_allowed") is False,
        acceptance_config.get("capital_movement_allowed") is False,
        acceptance_config.get("robinhood_execution_allowed") is False,
        acceptance_config.get("direct_database_writes") is False,
    ))
    stage("SAFETY_BOUNDARY", safety_safe, "No broker execution, capital movement, Robinhood execution, or database writes")

    final_result = "READY_FOR_CIO" if not errors and all(row["status"] == "PASS" for row in stages) else "NOT_READY_FOR_CIO"
    return {
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "acceptance_schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "plugin_id": PLUGIN_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "final_result": final_result,
        "stage_count": len(stages),
        "passed_stage_count": sum(1 for row in stages if row["status"] == "PASS"),
        "stages": stages,
        "decision_trace_replay": replay,
        "errors": errors,
        "warnings": [],
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Swing CIO Acceptance Report", "",
        f"- Final result: **{report.get('final_result')}**",
        f"- Plugin: `{report.get('plugin_id')}`",
        f"- Passed stages: {report.get('passed_stage_count')} / {report.get('stage_count')}", "",
        "## Acceptance Stages", "",
    ]
    for row in report.get("stages") or []:
        lines.append(f"- {row.get('stage')}: **{row.get('status')}** — {row.get('message')}")
    lines.extend(["", "## Errors", ""])
    errors = report.get("errors") or []
    lines.extend(f"- {item}" for item in errors) if errors else lines.append("- None")
    lines.extend(["", "Paper-only, advisory-only acceptance. No real orders or capital movement are performed.", ""])
    return "\n".join(lines)


def write_acceptance_report(report: Mapping[str, Any], output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "swing_cio_acceptance_report.json"
    md_path = output / "swing_cio_acceptance_report.md"
    json_path.write_text(json.dumps(dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}

"""Append-only, paper-only decision traceability for Swing committees."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_NAME = "swing_committee_traceability"
MODULE_VERSION = "1.0.0"
TRACE_SCHEMA_VERSION = "1.0"
PLUGIN_ID = "SWING-001"
COMMITTEE_SEQUENCE = (
    "DISCOVERY_COMMITTEE",
    "OPPORTUNITY_COMMITTEE",
    "ENTRY_COMMITTEE",
    "PORTFOLIO_COMMITTEE",
    "EXIT_COMMITTEE",
)
ALLOWED_STEP_STATUSES = {"PASS", "FAIL", "VETO", "SKIPPED", "NOT_APPLICABLE", "HOLD", "REVIEW", "EXIT"}
ALLOWED_FINAL_STATUSES = {"REJECTED", "WAIT", "ELIGIBLE_FOR_ALLOCATION", "ALLOCATED", "HOLD", "REVIEW", "EXIT"}
BIAS_FIELDS = (
    "sector_bias_applied",
    "theme_bias_applied",
    "concentration_limit_applied",
    "stock_history_bias_applied",
    "market_regime_veto_applied",
)


@dataclass(frozen=True, slots=True)
class TraceValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash(*parts: Any) -> str:
    raw = "|".join(_canonical(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_traceability_config(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Traceability configuration root must be an object")
    return payload


def validate_traceability_config(payload: Mapping[str, Any]) -> TraceValidationResult:
    errors: list[str] = []
    if payload.get("trace_schema_version") != TRACE_SCHEMA_VERSION:
        errors.append("trace_schema_version must be 1.0")
    if payload.get("plugin_id") != PLUGIN_ID:
        errors.append("plugin_id must be SWING-001")
    for field, expected in {
        "paper_trade_mode": True,
        "advisory_only": True,
        "append_only": True,
        "automatic_policy_change_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
    }.items():
        if payload.get(field) is not expected:
            errors.append(f"{field} must be {str(expected).lower()}")
    if tuple(payload.get("committee_sequence") or ()) != COMMITTEE_SEQUENCE:
        errors.append("committee_sequence must match the frozen five-committee order")
    if set(payload.get("allowed_step_statuses") or ()) != ALLOWED_STEP_STATUSES:
        errors.append("allowed_step_statuses do not match the frozen contract")
    if set(payload.get("allowed_final_statuses") or ()) != ALLOWED_FINAL_STATUSES:
        errors.append("allowed_final_statuses do not match the frozen contract")
    if tuple(payload.get("bias_audit_fields") or ()) != BIAS_FIELDS:
        errors.append("bias_audit_fields do not match the frozen contract")
    if payload.get("bias_audit_required_value") is not False:
        errors.append("bias_audit_required_value must be false")
    outcome = payload.get("outcome_attachment")
    if not isinstance(outcome, Mapping):
        errors.append("outcome_attachment must be an object")
    else:
        if outcome.get("append_only") is not True:
            errors.append("outcome_attachment.append_only must be true")
        if outcome.get("automatic_policy_change_allowed") is not False:
            errors.append("outcome attachment may not change policy automatically")
        if outcome.get("human_approval_required_for_policy_change") is not True:
            errors.append("human approval must be required for policy changes")
    return TraceValidationResult(not errors, tuple(errors), ())


def build_committee_step(
    *,
    evaluation_cycle_id: str,
    symbol: str,
    strategy_id: str,
    committee_id: str,
    sequence: int,
    status: str,
    reason_codes: Sequence[str] | None = None,
    evidence: Mapping[str, Any] | None = None,
    source_artifacts: Sequence[str] | None = None,
) -> dict[str, Any]:
    if committee_id not in COMMITTEE_SEQUENCE:
        raise ValueError(f"Unsupported committee_id: {committee_id}")
    expected_sequence = COMMITTEE_SEQUENCE.index(committee_id) + 1
    if sequence != expected_sequence:
        raise ValueError(f"{committee_id} sequence must be {expected_sequence}")
    normalized_status = str(status).upper()
    if normalized_status not in ALLOWED_STEP_STATUSES:
        raise ValueError(f"Unsupported step status: {status}")
    evidence_payload = dict(evidence or {})
    sources = sorted({str(item) for item in source_artifacts or [] if str(item).strip()})
    snapshot_hash = _hash(evaluation_cycle_id, symbol.upper(), strategy_id, committee_id, evidence_payload, sources)
    return {
        "committee_id": committee_id,
        "sequence": sequence,
        "status": normalized_status,
        "reason_codes": sorted({str(item).upper() for item in reason_codes or [] if str(item).strip()}),
        "evidence": evidence_payload,
        "source_artifacts": sources,
        "input_snapshot_hash": snapshot_hash,
        "step_id": f"SWING-STEP-{snapshot_hash[:16].upper()}",
    }


def build_decision_trace(
    *,
    evaluation_cycle_id: str,
    symbol: str,
    strategy_id: str,
    committee_steps: Sequence[Mapping[str, Any]],
    final_status: str,
    source_artifacts: Sequence[str] | None = None,
    bias_audit: Mapping[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    status = str(final_status).upper()
    if status not in ALLOWED_FINAL_STATUSES:
        raise ValueError(f"Unsupported final_status: {final_status}")
    steps = [dict(step) for step in committee_steps]
    trace_key = _hash(evaluation_cycle_id, symbol.upper(), strategy_id, steps)
    trace = {
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "plugin_id": PLUGIN_ID,
        "decision_trace_id": f"SWING-TRACE-{trace_key[:16].upper()}",
        "record_key": trace_key,
        "evaluation_cycle_id": str(evaluation_cycle_id),
        "symbol": str(symbol).upper(),
        "strategy_id": str(strategy_id).upper(),
        "generated_at_utc": generated_at_utc or _utc_now(),
        "committee_steps": steps,
        "final_status": status,
        "source_artifacts": sorted({str(item) for item in source_artifacts or [] if str(item).strip()}),
        "bias_audit": {field: bool((bias_audit or {}).get(field, False)) for field in BIAS_FIELDS},
        "paper_trade_mode": True,
        "advisory_only": True,
        "append_only": True,
        "automatic_policy_change_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
    }
    result = validate_decision_trace(trace)
    if not result.valid:
        raise ValueError("Invalid decision trace: " + "; ".join(result.errors))
    return trace


def validate_decision_trace(trace: Mapping[str, Any]) -> TraceValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    for field in ("decision_trace_id", "record_key", "evaluation_cycle_id", "symbol", "strategy_id", "generated_at_utc"):
        if not trace.get(field):
            errors.append(f"missing required field: {field}")
    for field, expected in {
        "paper_trade_mode": True,
        "advisory_only": True,
        "append_only": True,
        "automatic_policy_change_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
    }.items():
        if trace.get(field) is not expected:
            errors.append(f"{field} must be {str(expected).lower()}")
    if trace.get("plugin_id") != PLUGIN_ID:
        errors.append("plugin_id must be SWING-001")
    if trace.get("final_status") not in ALLOWED_FINAL_STATUSES:
        errors.append("invalid final_status")
    steps = trace.get("committee_steps")
    if not isinstance(steps, list) or not steps:
        errors.append("committee_steps must be a non-empty list")
        steps = []
    seen: set[str] = set()
    for index, step in enumerate(steps):
        prefix = f"committee_steps[{index}]"
        if not isinstance(step, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        committee_id = step.get("committee_id")
        if committee_id not in COMMITTEE_SEQUENCE:
            errors.append(f"{prefix} has unsupported committee_id")
            continue
        if committee_id in seen:
            errors.append(f"duplicate committee step: {committee_id}")
        seen.add(str(committee_id))
        expected_sequence = COMMITTEE_SEQUENCE.index(str(committee_id)) + 1
        if step.get("sequence") != expected_sequence:
            errors.append(f"{committee_id} sequence must be {expected_sequence}")
        if step.get("status") not in ALLOWED_STEP_STATUSES:
            errors.append(f"{committee_id} has invalid status")
        for required in ("reason_codes", "evidence", "source_artifacts", "input_snapshot_hash", "step_id"):
            if required not in step:
                errors.append(f"{committee_id} missing {required}")
    sequences = [step.get("sequence") for step in steps if isinstance(step, Mapping)]
    if sequences != sorted(sequences):
        errors.append("committee steps must be in sequence order")
    statuses = {step.get("committee_id"): step.get("status") for step in steps if isinstance(step, Mapping)}
    if statuses.get("OPPORTUNITY_COMMITTEE") in {"FAIL", "VETO"}:
        for later in ("ENTRY_COMMITTEE", "PORTFOLIO_COMMITTEE"):
            if statuses.get(later) not in {None, "SKIPPED", "NOT_APPLICABLE"}:
                errors.append(f"{later} must be skipped after Opportunity rejection")
    if statuses.get("ENTRY_COMMITTEE") in {"FAIL", "VETO"} and statuses.get("PORTFOLIO_COMMITTEE") not in {None, "SKIPPED", "NOT_APPLICABLE"}:
        errors.append("PORTFOLIO_COMMITTEE must be skipped after Entry veto")
    bias = trace.get("bias_audit")
    if not isinstance(bias, Mapping):
        errors.append("bias_audit must be an object")
    else:
        for field in BIAS_FIELDS:
            if bias.get(field) is not False:
                errors.append(f"{field} must be false")
    if not trace.get("source_artifacts"):
        warnings.append("No top-level source artifacts were recorded")
    return TraceValidationResult(not errors, tuple(errors), tuple(warnings))


def build_outcome_attachment(
    *,
    decision_trace_id: str,
    measurement_horizon: str,
    metrics: Mapping[str, Any],
    source_artifacts: Sequence[str],
    measured_at_utc: str | None = None,
) -> dict[str, Any]:
    measured_at = measured_at_utc or _utc_now()
    record_key = _hash(decision_trace_id, measurement_horizon, metrics, sorted(source_artifacts))
    return {
        "outcome_id": f"SWING-OUTCOME-{record_key[:16].upper()}",
        "record_key": record_key,
        "decision_trace_id": decision_trace_id,
        "measurement_horizon": str(measurement_horizon).upper(),
        "measured_at_utc": measured_at,
        "metrics": dict(metrics),
        "source_artifacts": sorted({str(item) for item in source_artifacts if str(item).strip()}),
        "append_only": True,
        "paper_trade_mode": True,
        "advisory_only": True,
        "automatic_policy_change_allowed": False,
    }


def append_unique_outcomes(existing: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = [dict(item) for item in existing]
    keys = {str(item.get("record_key")) for item in records if item.get("record_key")}
    for item in new:
        row = dict(item)
        key = str(row.get("record_key") or "")
        if not key:
            raise ValueError("Outcome record_key is required")
        if key not in keys:
            records.append(row)
            keys.add(key)
    return records


def write_decision_trace(trace: Mapping[str, Any], output_path: str | Path) -> Path:
    result = validate_decision_trace(trace)
    if not result.valid:
        raise ValueError("Invalid decision trace: " + "; ".join(result.errors))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(trace), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

"""Governed, append-only committee learning for the paper-only Swing Bot."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_NAME = "swing_committee_learning"
MODULE_VERSION = "1.0.0"
LEARNING_SCHEMA_VERSION = "1.0"
PLUGIN_ID = "SWING-001"
COMMITTEES = (
    "DISCOVERY_COMMITTEE",
    "OPPORTUNITY_COMMITTEE",
    "ENTRY_COMMITTEE",
    "PORTFOLIO_COMMITTEE",
    "EXIT_COMMITTEE",
)
MIN_COMPLETED_TRACES = 30
MIN_HISTORY_MONTHS = 6
MIN_OBSERVATIONS_PER_COMMITTEE = 10
PROPOSAL_TYPES = {
    "EVIDENCE_SOURCE_REVIEW",
    "THRESHOLD_REVIEW",
    "COMMITTEE_PROCESS_REVIEW",
    "STRATEGY_PREFERENCE_REVIEW",
    "NO_CHANGE",
}


@dataclass(frozen=True, slots=True)
class LearningValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _stable_hash(*parts: Any) -> str:
    raw = "|".join(_canonical(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def load_committee_learning_config(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Committee learning configuration root must be an object")
    return payload


def validate_committee_learning_config(payload: Mapping[str, Any]) -> LearningValidationResult:
    errors: list[str] = []
    expected = {
        "learning_schema_version": LEARNING_SCHEMA_VERSION,
        "plugin_id": PLUGIN_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "append_only": True,
        "automatic_policy_change_allowed": False,
        "human_approval_required": True,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            errors.append(f"{field} must be {value}")
    if tuple(payload.get("committee_sequence") or ()) != COMMITTEES:
        errors.append("committee_sequence must match the frozen committee order")
    minimum = payload.get("minimum_evidence")
    if not isinstance(minimum, Mapping):
        errors.append("minimum_evidence must be an object")
    else:
        locked = {
            "completed_decision_traces": MIN_COMPLETED_TRACES,
            "history_months": MIN_HISTORY_MONTHS,
            "observations_per_committee": MIN_OBSERVATIONS_PER_COMMITTEE,
        }
        for field, value in locked.items():
            if minimum.get(field) != value:
                errors.append(f"minimum_evidence.{field} must be {value}")
    proposal_types = set(payload.get("proposal_types") or [])
    if proposal_types != PROPOSAL_TYPES:
        errors.append("proposal_types must match the frozen governed set")
    return LearningValidationResult(not errors, tuple(errors), ())


def build_committee_observation(
    *,
    decision_trace_id: str,
    committee_id: str,
    strategy_id: str,
    decision_status: str,
    decision_quality: Mapping[str, Any],
    outcome_quality: Mapping[str, Any],
    measurement_horizon: str,
    source_artifacts: Sequence[str],
    observed_at_utc: str | None = None,
) -> dict[str, Any]:
    if committee_id not in COMMITTEES:
        raise ValueError(f"Unsupported committee_id: {committee_id}")
    if not decision_trace_id:
        raise ValueError("decision_trace_id is required")
    observed_at = observed_at_utc or _utc_now()
    payload = {
        "decision_trace_id": decision_trace_id,
        "committee_id": committee_id,
        "strategy_id": str(strategy_id).upper(),
        "decision_status": str(decision_status).upper(),
        "decision_quality": dict(decision_quality),
        "outcome_quality": dict(outcome_quality),
        "measurement_horizon": measurement_horizon,
        "source_artifacts": list(source_artifacts),
    }
    key = _stable_hash(payload)
    return {
        "observation_id": f"SWING-OBS-{key[:16].upper()}",
        "record_key": key,
        **payload,
        "observed_at_utc": observed_at,
        "append_only": True,
        "paper_trade_mode": True,
        "advisory_only": True,
        "automatic_policy_change_allowed": False,
    }


def append_unique_observations(
    existing: Sequence[Mapping[str, Any]],
    incoming: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = [dict(row) for row in existing]
    keys = {str(row.get("record_key")) for row in result if row.get("record_key")}
    for row in incoming:
        key = str(row.get("record_key") or "")
        if not key:
            raise ValueError("Every observation requires record_key")
        if key not in keys:
            result.append(dict(row))
            keys.add(key)
    return result


def summarize_committee_learning(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for committee_id in COMMITTEES:
        rows = [row for row in observations if row.get("committee_id") == committee_id]
        if not rows:
            continue
        compliant = sum(1 for row in rows if bool(row.get("decision_quality", {}).get("policy_compliant", False)))
        complete = sum(1 for row in rows if bool(row.get("decision_quality", {}).get("evidence_complete", False)))
        returns = [_number(row.get("outcome_quality", {}).get("return_percent")) for row in rows]
        mfe = [_number(row.get("outcome_quality", {}).get("maximum_favorable_excursion_percent")) for row in rows]
        mae = [_number(row.get("outcome_quality", {}).get("maximum_adverse_excursion_percent")) for row in rows]
        count = len(rows)
        summaries.append({
            "committee_id": committee_id,
            "observation_count": count,
            "policy_compliance_rate_percent": round(compliant * 100.0 / count, 2),
            "evidence_completeness_rate_percent": round(complete * 100.0 / count, 2),
            "average_return_percent": round(sum(returns) / count, 4),
            "average_maximum_favorable_excursion_percent": round(sum(mfe) / count, 4),
            "average_maximum_adverse_excursion_percent": round(sum(mae) / count, 4),
        })
    return summaries


def evidence_is_sufficient(
    *, completed_decision_traces: int,
    history_months: int,
    committee_summaries: Sequence[Mapping[str, Any]],
) -> bool:
    if completed_decision_traces < MIN_COMPLETED_TRACES or history_months < MIN_HISTORY_MONTHS:
        return False
    by_id = {str(row.get("committee_id")): int(row.get("observation_count", 0)) for row in committee_summaries}
    return all(by_id.get(committee_id, 0) >= MIN_OBSERVATIONS_PER_COMMITTEE for committee_id in COMMITTEES)


def generate_learning_proposals(
    committee_summaries: Sequence[Mapping[str, Any]],
    *, evidence_sufficient: bool,
) -> list[dict[str, Any]]:
    if not evidence_sufficient:
        return []
    proposals: list[dict[str, Any]] = []
    for row in committee_summaries:
        committee_id = str(row.get("committee_id"))
        compliance = _number(row.get("policy_compliance_rate_percent"))
        completeness = _number(row.get("evidence_completeness_rate_percent"))
        average_mae = _number(row.get("average_maximum_adverse_excursion_percent"))
        if compliance < 100.0:
            proposals.append(_proposal("COMMITTEE_PROCESS_REVIEW", committee_id, "Policy compliance fell below 100%.", row))
        if completeness < 90.0:
            proposals.append(_proposal("EVIDENCE_SOURCE_REVIEW", committee_id, "Evidence completeness fell below 90%.", row))
        if committee_id == "ENTRY_COMMITTEE" and average_mae < -5.0:
            proposals.append(_proposal("THRESHOLD_REVIEW", committee_id, "Entry outcomes show average adverse excursion below -5%; review timing thresholds.", row))
    if not proposals:
        proposals.append(_proposal("NO_CHANGE", "COMMITTEE_POLICY", "Available evidence does not support a policy change.", {"observation_count": sum(int(r.get("observation_count", 0)) for r in committee_summaries)}))
    return proposals


def _proposal(proposal_type: str, target: str, summary: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    if proposal_type not in PROPOSAL_TYPES:
        raise ValueError(f"Unsupported proposal_type: {proposal_type}")
    key = _stable_hash(proposal_type, target, summary, evidence)
    return {
        "proposal_id": f"SWING-LEARN-{key[:16].upper()}",
        "proposal_type": proposal_type,
        "target": target,
        "evidence_summary": summary,
        "evidence": dict(evidence),
        "status": "WAITING_FOR_APPROVAL",
        "requires_human_approval": True,
        "automatic_policy_change": False,
    }


def build_committee_learning_report(
    *,
    observations: Sequence[Mapping[str, Any]] | None = None,
    completed_decision_traces: int = 0,
    history_months: int = 0,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    rows = [dict(row) for row in observations or []]
    summaries = summarize_committee_learning(rows)
    sufficient = evidence_is_sufficient(
        completed_decision_traces=completed_decision_traces,
        history_months=history_months,
        committee_summaries=summaries,
    )
    proposals = generate_learning_proposals(summaries, evidence_sufficient=sufficient)
    warnings = [] if sufficient else ["Minimum evidence requirements have not been met; learning remains observation-only."]
    return {
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "learning_schema_version": LEARNING_SCHEMA_VERSION,
        "plugin_id": PLUGIN_ID,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "paper_trade_mode": True,
        "advisory_only": True,
        "append_only": True,
        "automatic_policy_change_allowed": False,
        "human_approval_required": True,
        "learning_status": "ELIGIBLE_FOR_REVIEW" if sufficient else "OBSERVATION_ONLY",
        "evidence_summary": {
            "completed_decision_traces": int(completed_decision_traces),
            "history_months": int(history_months),
            "evidence_sufficient": sufficient,
        },
        "committee_summaries": summaries,
        "learning_proposals": proposals,
        "proposal_count": len(proposals),
        "warnings": warnings,
    }


def write_committee_learning_report(report: Mapping[str, Any], output_path: str | Path) -> Path:
    if report.get("paper_trade_mode") is not True or report.get("automatic_policy_change_allowed") is not False:
        raise ValueError("Unsafe committee learning report")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

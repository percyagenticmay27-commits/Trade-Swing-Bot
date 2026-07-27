"""Evidence-only, paper-only committee governance for the Swing Bot."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "swing_committee_governance"
MODULE_VERSION = "1.0.0"
GOVERNANCE_SCHEMA_VERSION = "1.0"
PLUGIN_ID = "SWING-001"
REQUIRED_COMMITTEES = (
    "DISCOVERY_COMMITTEE",
    "OPPORTUNITY_COMMITTEE",
    "ENTRY_COMMITTEE",
    "PORTFOLIO_COMMITTEE",
    "EXIT_COMMITTEE",
)


@dataclass(frozen=True, slots=True)
class GovernanceValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def load_committee_governance(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Committee governance root must be an object")
    return payload


def validate_committee_governance(payload: Mapping[str, Any]) -> GovernanceValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    locked_values = {
        "governance_schema_version": GOVERNANCE_SCHEMA_VERSION,
        "plugin_id": PLUGIN_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "automatic_activation_allowed": False,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
        "decision_model": "SEQUENTIAL_INDEPENDENT_COMMITTEES",
        "evidence_only_allocation": True,
        "sector_bias_allowed": False,
        "theme_concentration_limits_allowed": False,
        "market_regime_hard_veto_allowed": False,
        "stock_history_bias_allowed": False,
        "final_eligibility_rule": "OPPORTUNITY_APPROVED_AND_ENTRY_APPROVED",
    }
    for field, expected in locked_values.items():
        if payload.get(field) != expected:
            errors.append(f"{field} must be {expected!r}")

    committees = payload.get("committees")
    if not isinstance(committees, list):
        errors.append("committees must be a list")
        committees = []

    seen: set[str] = set()
    sequences: list[int] = []
    by_id: dict[str, Mapping[str, Any]] = {}
    for index, committee in enumerate(committees):
        prefix = f"committees[{index}]"
        if not isinstance(committee, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        committee_id = committee.get("committee_id")
        if not isinstance(committee_id, str) or not committee_id:
            errors.append(f"{prefix}.committee_id must be a non-empty string")
            continue
        if committee_id in seen:
            errors.append(f"Duplicate committee_id: {committee_id}")
        seen.add(committee_id)
        by_id[committee_id] = committee
        sequence = committee.get("sequence")
        if not isinstance(sequence, int):
            errors.append(f"{committee_id}.sequence must be an integer")
        else:
            sequences.append(sequence)
        for field in ("jurisdiction", "question", "produces", "prohibited_actions"):
            if committee.get(field) in (None, "", []):
                errors.append(f"{committee_id}.{field} is required")

    if tuple(c.get("committee_id") for c in committees if isinstance(c, Mapping)) != REQUIRED_COMMITTEES:
        errors.append("committees must appear in the required governance sequence")
    if sequences != list(range(1, len(REQUIRED_COMMITTEES) + 1)):
        errors.append("committee sequence values must be 1 through 5")

    _validate_opportunity_committee(by_id.get("OPPORTUNITY_COMMITTEE"), errors)
    _validate_entry_committee(by_id.get("ENTRY_COMMITTEE"), errors)
    _validate_portfolio_committee(by_id.get("PORTFOLIO_COMMITTEE"), errors)
    _validate_exit_committee(by_id.get("EXIT_COMMITTEE"), errors)

    independence = payload.get("committee_independence_rules")
    if not isinstance(independence, list) or "ENTRY_IS_NOT_BLENDED_INTO_OPPORTUNITY_QUALITY" not in independence:
        errors.append("committee independence must keep Entry separate from Opportunity Quality")
    if isinstance(committees, list) and len(committees) > len(REQUIRED_COMMITTEES):
        warnings.append("Additional committees require CIO governance approval")

    return GovernanceValidationResult(not errors, tuple(errors), tuple(warnings))


def get_committee(payload: Mapping[str, Any], committee_id: str) -> dict[str, Any]:
    for committee in payload.get("committees", []):
        if isinstance(committee, Mapping) and committee.get("committee_id") == committee_id:
            return dict(committee)
    raise KeyError(f"Unknown committee: {committee_id}")


def evaluate_trade_gate(
    payload: Mapping[str, Any],
    *,
    opportunity_quality_score: float,
    entry_score: float,
    thesis_intact: bool,
) -> dict[str, object]:
    """Evaluate the independent Opportunity and Entry gates without blending scores."""
    result = validate_committee_governance(payload)
    if not result.valid:
        raise ValueError("Invalid committee governance: " + "; ".join(result.errors))
    opportunity = opportunity_quality_score >= 70.0
    entry = entry_score >= 70.0 and thesis_intact
    return {
        "opportunity_approved": opportunity,
        "entry_approved": entry,
        "eligible_for_portfolio_committee": opportunity and entry,
        "opportunity_quality_score": float(opportunity_quality_score),
        "entry_score": float(entry_score),
        "thesis_intact": bool(thesis_intact),
    }


def build_governance_summary(payload: Mapping[str, Any]) -> dict[str, object]:
    committees = [c for c in payload.get("committees", []) if isinstance(c, Mapping)]
    return {
        "plugin_id": payload.get("plugin_id"),
        "policy_version": payload.get("policy_version"),
        "committee_count": len(committees),
        "committee_ids": [c.get("committee_id") for c in committees],
        "decision_model": payload.get("decision_model"),
        "evidence_only_allocation": payload.get("evidence_only_allocation"),
        "paper_trade_mode": payload.get("paper_trade_mode"),
        "advisory_only": payload.get("advisory_only"),
    }


def write_committee_governance(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    result = validate_committee_governance(payload)
    if not result.valid:
        raise ValueError("Invalid committee governance: " + "; ".join(result.errors))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _validate_opportunity_committee(committee: Mapping[str, Any] | None, errors: list[str]) -> None:
    if committee is None:
        errors.append("Missing OPPORTUNITY_COMMITTEE")
        return
    expected = {
        "minimum_opportunity_quality_score": 70.0,
        "entry_score_included_in_opportunity_quality": False,
        "sector_or_theme_adjustment_allowed": False,
        "market_regime_hard_gate_allowed": False,
    }
    _require_values("OPPORTUNITY_COMMITTEE", committee, expected, errors)


def _validate_entry_committee(committee: Mapping[str, Any] | None, errors: list[str]) -> None:
    if committee is None:
        errors.append("Missing ENTRY_COMMITTEE")
        return
    expected = {
        "minimum_entry_score": 70.0,
        "opportunity_must_be_eligible": True,
        "thesis_must_be_intact": True,
        "market_regime_hard_gate_allowed": False,
    }
    _require_values("ENTRY_COMMITTEE", committee, expected, errors)
    timing = committee.get("timing_evidence")
    required = {"DAILY_RSI_DIRECTION", "DAILY_STOCHASTIC_RSI_K_D_RELATIONSHIP"}
    if not isinstance(timing, list) or not required.issubset(set(timing)):
        errors.append("ENTRY_COMMITTEE must include daily RSI and Stochastic RSI timing evidence")


def _validate_portfolio_committee(committee: Mapping[str, Any] | None, errors: list[str]) -> None:
    if committee is None:
        errors.append("Missing PORTFOLIO_COMMITTEE")
        return
    expected = {
        "allocation_priority": "OPPORTUNITY_RANK_DESCENDING",
        "higher_rank_receives_more_capital": True,
        "fixed_position_count_required": False,
        "sector_or_theme_adjustment_allowed": False,
        "theme_concentration_limits_allowed": False,
        "market_regime_allocation_adjustment_allowed": False,
        "stock_identity_adjustment_allowed": False,
        "historical_reputation_adjustment_allowed": False,
        "unallocated_capital_destination": "SGOV",
    }
    _require_values("PORTFOLIO_COMMITTEE", committee, expected, errors)


def _validate_exit_committee(committee: Mapping[str, Any] | None, errors: list[str]) -> None:
    if committee is None:
        errors.append("Missing EXIT_COMMITTEE")
        return
    expected = {
        "strategy_specific_rules_required": True,
        "replacement_requires_better_entry_approved_opportunity": True,
        "sector_or_theme_exit_allowed": False,
        "market_regime_only_exit_allowed": False,
    }
    _require_values("EXIT_COMMITTEE", committee, expected, errors)


def _require_values(name: str, payload: Mapping[str, Any], expected: Mapping[str, Any], errors: list[str]) -> None:
    for field, value in expected.items():
        if payload.get(field) != value:
            errors.append(f"{name}.{field} must be {value!r}")

"""Strict, paper-only capability profiles for Swing Strategy A and Strategy B."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "swing_strategy_capability_profiles"
MODULE_VERSION = "1.1.0"
PROFILE_SCHEMA_VERSION = "1.0"
VERSION_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
REQUIRED_STRATEGIES = {"STRATEGY_A", "STRATEGY_B"}
SUPPORTED_ASSETS = {"STOCKS", "LEVERAGED_ETFS"}
RISK_STYLES = {"CONSERVATIVE", "MODERATE", "AGGRESSIVE"}
PROTECTION_LEVELS = {"LOW", "MEDIUM", "HIGH"}


@dataclass(frozen=True, slots=True)
class CapabilityValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def load_strategy_capability_profiles(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Capability profile root must be an object")
    return payload


def validate_strategy_capability_profiles(payload: Mapping[str, Any]) -> CapabilityValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("profile_schema_version") != PROFILE_SCHEMA_VERSION:
        errors.append("profile_schema_version must be 1.0")
    if payload.get("plugin_id") != "SWING-001":
        errors.append("plugin_id must be SWING-001")
    if payload.get("paper_trade_mode") is not True:
        errors.append("paper_trade_mode must be true")
    if payload.get("advisory_only") is not True:
        errors.append("advisory_only must be true")
    if payload.get("automatic_activation_allowed") is not False:
        errors.append("automatic_activation_allowed must be false")
    if payload.get("committee_governance_policy") != "configs/swing_committee_governance.json":
        errors.append("committee_governance_policy must reference configs/swing_committee_governance.json")

    profiles = payload.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        errors.append("profiles must be a non-empty list")
        profiles = []

    seen: set[str] = set()
    for index, profile in enumerate(profiles):
        prefix = f"profiles[{index}]"
        if not isinstance(profile, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        required = (
            "strategy_id", "display_name", "strategy_version", "purpose",
            "entry_philosophy", "exit_philosophy", "risk_style",
            "capital_protection_level", "reentry_supported",
            "typical_holding_period", "supported_assets", "entry_rules",
            "exit_review_rules", "profit_protection_rules",
        )
        for field in required:
            if profile.get(field) in (None, ""):
                errors.append(f"{prefix} missing required field: {field}")

        strategy_id = str(profile.get("strategy_id", ""))
        if strategy_id in seen:
            errors.append(f"Duplicate strategy_id: {strategy_id}")
        seen.add(strategy_id)
        if strategy_id not in REQUIRED_STRATEGIES:
            errors.append(f"Unsupported strategy_id: {strategy_id}")

        version = profile.get("strategy_version")
        if not isinstance(version, str) or VERSION_PATTERN.fullmatch(version) is None:
            errors.append(f"Invalid strategy_version for {strategy_id}: {version}")
        if profile.get("risk_style") not in RISK_STYLES:
            errors.append(f"Invalid risk_style for {strategy_id}")
        if profile.get("capital_protection_level") not in PROTECTION_LEVELS:
            errors.append(f"Invalid capital_protection_level for {strategy_id}")

        assets = profile.get("supported_assets")
        if not isinstance(assets, list) or not assets:
            errors.append(f"{strategy_id} supported_assets must be a non-empty list")
        else:
            if len(assets) != len(set(assets)):
                errors.append(f"{strategy_id} supported_assets contains duplicates")
            unknown = sorted(set(assets) - SUPPORTED_ASSETS)
            if unknown:
                errors.append(f"{strategy_id} has unsupported assets: {', '.join(unknown)}")

        _validate_entry_rules(profile, strategy_id, errors)
        _validate_profit_rules(profile, strategy_id, errors)
        _validate_exit_bias_rules(profile, strategy_id, errors)

        if strategy_id == "STRATEGY_A":
            if profile.get("reentry_supported") is not False:
                errors.append("STRATEGY_A reentry_supported must be false")
            if profile.get("exit_review_rules", {}).get("hard_loss_exit_percent") is not None:
                errors.append("STRATEGY_A must not define a hard numerical loss exit")
        if strategy_id == "STRATEGY_B":
            if profile.get("reentry_supported") is not True:
                errors.append("STRATEGY_B reentry_supported must be true")
            if profile.get("exit_review_rules", {}).get("hard_loss_exit_percent") != 10.0:
                errors.append("STRATEGY_B hard_loss_exit_percent must be 10.0")
            _validate_reentry_rules(profile, errors)

    missing = REQUIRED_STRATEGIES - seen
    if missing:
        errors.append(f"Missing required strategy profiles: {', '.join(sorted(missing))}")
    if len(profiles) > len(REQUIRED_STRATEGIES):
        warnings.append("Additional strategies require CIO governance review before activation")

    return CapabilityValidationResult(not errors, tuple(errors), tuple(warnings))


def get_strategy_profile(payload: Mapping[str, Any], strategy_id: str) -> dict[str, Any]:
    for profile in payload.get("profiles", []):
        if isinstance(profile, Mapping) and profile.get("strategy_id") == strategy_id:
            return dict(profile)
    raise KeyError(f"Unknown strategy profile: {strategy_id}")


def list_profiles_for_asset(payload: Mapping[str, Any], asset_type: str) -> list[dict[str, Any]]:
    return [
        dict(profile)
        for profile in payload.get("profiles", [])
        if isinstance(profile, Mapping) and asset_type in profile.get("supported_assets", [])
    ]


def build_capability_summary(payload: Mapping[str, Any]) -> dict[str, object]:
    profiles = [p for p in payload.get("profiles", []) if isinstance(p, Mapping)]
    return {
        "plugin_id": payload.get("plugin_id"),
        "profile_count": len(profiles),
        "strategy_ids": sorted(str(p.get("strategy_id")) for p in profiles),
        "reentry_capable_strategies": sorted(
            str(p.get("strategy_id")) for p in profiles if p.get("reentry_supported") is True
        ),
        "committee_governance_policy": payload.get("committee_governance_policy"),
        "paper_trade_mode": payload.get("paper_trade_mode"),
        "advisory_only": payload.get("advisory_only"),
    }


def write_strategy_capability_profiles(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    result = validate_strategy_capability_profiles(payload)
    if not result.valid:
        raise ValueError("Invalid strategy capability profiles: " + "; ".join(result.errors))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _validate_entry_rules(profile: Mapping[str, Any], strategy_id: str, errors: list[str]) -> None:
    rules = profile.get("entry_rules")
    if not isinstance(rules, Mapping):
        errors.append(f"{strategy_id} entry_rules must be an object")
        return
    expected = {
        "minimum_opportunity_quality_score": 70.0,
        "minimum_entry_score": 70.0,
        "thesis_must_be_intact": True,
        "market_regime_hard_gate_allowed": False,
        "entry_score_is_independent_veto": True,
    }
    for field, value in expected.items():
        if rules.get(field) != value:
            errors.append(f"{strategy_id} entry_rules.{field} must be {value}")
    if "minimum_market_regime_score" in rules:
        errors.append(f"{strategy_id} entry_rules must not define a minimum_market_regime_score")


def _validate_profit_rules(profile: Mapping[str, Any], strategy_id: str, errors: list[str]) -> None:
    rules = profile.get("profit_protection_rules")
    expected = {
        "standard_gain_percent": 20.0,
        "standard_giveback_percent": 5.0,
        "strong_gain_percent": 30.0,
        "strong_giveback_percent": 10.0,
    }
    if not isinstance(rules, Mapping):
        errors.append(f"{strategy_id} profit_protection_rules must be an object")
        return
    for field, value in expected.items():
        if rules.get(field) != value:
            errors.append(f"{strategy_id} profit_protection_rules.{field} must be {value}")


def _validate_exit_bias_rules(profile: Mapping[str, Any], strategy_id: str, errors: list[str]) -> None:
    rules = profile.get("exit_review_rules")
    if not isinstance(rules, Mapping):
        errors.append(f"{strategy_id} exit_review_rules must be an object")
        return
    if rules.get("market_regime_only_exit_allowed") is not False:
        errors.append(f"{strategy_id} market_regime_only_exit_allowed must be false")
    if rules.get("sector_or_theme_exit_allowed") is not False:
        errors.append(f"{strategy_id} sector_or_theme_exit_allowed must be false")


def _validate_reentry_rules(profile: Mapping[str, Any], errors: list[str]) -> None:
    rules = profile.get("reentry_rules")
    expected = {
        "minimum_wait_days": 3,
        "minimum_opportunity_quality_score": 70.0,
        "minimum_entry_score": 70.0,
        "maximum_distance_from_reentry_level_percent": 3.0,
        "thesis_must_be_intact": True,
        "market_regime_hard_gate_allowed": False,
        "entry_score_is_independent_veto": True,
    }
    if not isinstance(rules, Mapping):
        errors.append("STRATEGY_B reentry_rules must be an object")
        return
    for field, value in expected.items():
        if rules.get(field) != value:
            errors.append(f"STRATEGY_B reentry_rules.{field} must be {value}")
    if "minimum_market_regime_score" in rules:
        errors.append("STRATEGY_B reentry_rules must not define a minimum_market_regime_score")

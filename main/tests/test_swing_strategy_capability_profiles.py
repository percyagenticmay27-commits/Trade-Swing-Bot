from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from swing_trade_bot.swing_strategy_capability_profiles import (
    build_capability_summary,
    get_strategy_profile,
    list_profiles_for_asset,
    load_strategy_capability_profiles,
    validate_strategy_capability_profiles,
    write_strategy_capability_profiles,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "swing_strategy_capability_profiles.json"


@pytest.fixture()
def payload() -> dict:
    return load_strategy_capability_profiles(CONFIG)


def test_config_loads(payload):
    assert payload["plugin_id"] == "SWING-001"


def test_valid_profiles_pass(payload):
    assert validate_strategy_capability_profiles(payload).valid is True


def test_profile_schema_is_locked(payload):
    assert payload["profile_schema_version"] == "1.0"


def test_paper_trade_mode_is_locked(payload):
    assert payload["paper_trade_mode"] is True


def test_advisory_only_is_locked(payload):
    assert payload["advisory_only"] is True


def test_automatic_activation_is_disabled(payload):
    assert payload["automatic_activation_allowed"] is False


def test_committee_governance_policy_is_linked(payload):
    assert payload["committee_governance_policy"] == "configs/swing_committee_governance.json"


def test_exactly_two_required_profiles(payload):
    assert {p["strategy_id"] for p in payload["profiles"]} == {"STRATEGY_A", "STRATEGY_B"}


def test_strategy_versions_are_1_4(payload):
    assert {p["strategy_version"] for p in payload["profiles"]} == {"1.4"}


def test_strategy_a_has_no_hard_loss_exit(payload):
    assert get_strategy_profile(payload, "STRATEGY_A")["exit_review_rules"]["hard_loss_exit_percent"] is None


def test_strategy_a_has_no_reentry(payload):
    assert get_strategy_profile(payload, "STRATEGY_A")["reentry_supported"] is False


def test_strategy_b_has_ten_percent_loss_review(payload):
    assert get_strategy_profile(payload, "STRATEGY_B")["exit_review_rules"]["hard_loss_exit_percent"] == 10.0


def test_strategy_b_supports_reentry(payload):
    assert get_strategy_profile(payload, "STRATEGY_B")["reentry_supported"] is True


def test_strategy_b_reentry_wait_is_three_days(payload):
    assert get_strategy_profile(payload, "STRATEGY_B")["reentry_rules"]["minimum_wait_days"] == 3


def test_shared_entry_thresholds_and_independent_veto(payload):
    for profile in payload["profiles"]:
        rules = profile["entry_rules"]
        assert rules["minimum_opportunity_quality_score"] == 70.0
        assert rules["minimum_entry_score"] == 70.0
        assert rules["thesis_must_be_intact"] is True
        assert rules["market_regime_hard_gate_allowed"] is False
        assert rules["entry_score_is_independent_veto"] is True
        assert "minimum_market_regime_score" not in rules


def test_reentry_has_no_market_regime_hard_gate(payload):
    rules = get_strategy_profile(payload, "STRATEGY_B")["reentry_rules"]
    assert rules["market_regime_hard_gate_allowed"] is False
    assert "minimum_market_regime_score" not in rules


def test_sector_or_regime_only_exit_is_forbidden(payload):
    for profile in payload["profiles"]:
        rules = profile["exit_review_rules"]
        assert rules["market_regime_only_exit_allowed"] is False
        assert rules["sector_or_theme_exit_allowed"] is False


def test_shared_profit_protection_thresholds(payload):
    for profile in payload["profiles"]:
        assert profile["profit_protection_rules"] == {
            "standard_gain_percent": 20.0,
            "standard_giveback_percent": 5.0,
            "strong_gain_percent": 30.0,
            "strong_giveback_percent": 10.0,
        }


def test_supported_assets_include_stocks_and_leveraged_etfs(payload):
    profiles = list_profiles_for_asset(payload, "LEVERAGED_ETFS")
    assert {p["strategy_id"] for p in profiles} == {"STRATEGY_A", "STRATEGY_B"}


def test_unknown_profile_raises(payload):
    with pytest.raises(KeyError):
        get_strategy_profile(payload, "STRATEGY_C")


@pytest.mark.parametrize("field,bad_value", [
    ("paper_trade_mode", False),
    ("advisory_only", False),
    ("automatic_activation_allowed", True),
    ("plugin_id", "BAD"),
    ("committee_governance_policy", "wrong.json"),
])
def test_top_level_safety_and_identity_rejected(payload, field, bad_value):
    changed = copy.deepcopy(payload)
    changed[field] = bad_value
    assert validate_strategy_capability_profiles(changed).valid is False


def test_duplicate_strategy_id_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"][1]["strategy_id"] = "STRATEGY_A"
    result = validate_strategy_capability_profiles(changed)
    assert not result.valid
    assert any("Duplicate strategy_id" in e for e in result.errors)


def test_missing_strategy_b_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"] = changed["profiles"][:1]
    assert validate_strategy_capability_profiles(changed).valid is False


def test_unknown_asset_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"][0]["supported_assets"].append("OPTIONS")
    assert validate_strategy_capability_profiles(changed).valid is False


def test_duplicate_asset_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"][0]["supported_assets"].append("STOCKS")
    assert validate_strategy_capability_profiles(changed).valid is False


def test_strategy_a_hard_stop_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"][0]["exit_review_rules"]["hard_loss_exit_percent"] = 10.0
    assert validate_strategy_capability_profiles(changed).valid is False


def test_strategy_b_wrong_stop_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"][1]["exit_review_rules"]["hard_loss_exit_percent"] = 8.0
    assert validate_strategy_capability_profiles(changed).valid is False


def test_strategy_b_missing_reentry_rules_rejected(payload):
    changed = copy.deepcopy(payload)
    del changed["profiles"][1]["reentry_rules"]
    assert validate_strategy_capability_profiles(changed).valid is False


def test_bad_entry_threshold_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"][0]["entry_rules"]["minimum_entry_score"] = 65.0
    assert validate_strategy_capability_profiles(changed).valid is False


def test_market_regime_minimum_is_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"][0]["entry_rules"]["minimum_market_regime_score"] = 50.0
    assert validate_strategy_capability_profiles(changed).valid is False


def test_sector_exit_bias_is_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"][0]["exit_review_rules"]["sector_or_theme_exit_allowed"] = True
    assert validate_strategy_capability_profiles(changed).valid is False


def test_bad_profit_threshold_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["profiles"][0]["profit_protection_rules"]["strong_gain_percent"] = 25.0
    assert validate_strategy_capability_profiles(changed).valid is False


def test_summary_identifies_reentry_strategy(payload):
    summary = build_capability_summary(payload)
    assert summary["profile_count"] == 2
    assert summary["reentry_capable_strategies"] == ["STRATEGY_B"]
    assert summary["committee_governance_policy"] == "configs/swing_committee_governance.json"


def test_write_profiles(payload, tmp_path):
    output = write_strategy_capability_profiles(payload, tmp_path / "results" / "profiles.json")
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["plugin_id"] == "SWING-001"


def test_invalid_profiles_are_not_written(payload, tmp_path):
    changed = copy.deepcopy(payload)
    changed["paper_trade_mode"] = False
    with pytest.raises(ValueError):
        write_strategy_capability_profiles(changed, tmp_path / "profiles.json")

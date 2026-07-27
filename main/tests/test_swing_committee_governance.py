from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from swing_trade_bot.swing_committee_governance import (
    build_governance_summary,
    evaluate_trade_gate,
    get_committee,
    load_committee_governance,
    validate_committee_governance,
    write_committee_governance,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "swing_committee_governance.json"


@pytest.fixture()
def payload() -> dict:
    return load_committee_governance(CONFIG)


def test_governance_config_is_valid(payload):
    assert validate_committee_governance(payload).valid is True


def test_paper_only_safety_locks(payload):
    assert payload["paper_trade_mode"] is True
    assert payload["advisory_only"] is True
    assert payload["automatic_activation_allowed"] is False
    assert payload["broker_execution_allowed"] is False
    assert payload["capital_movement_allowed"] is False


def test_required_committee_sequence(payload):
    assert [c["committee_id"] for c in payload["committees"]] == [
        "DISCOVERY_COMMITTEE",
        "OPPORTUNITY_COMMITTEE",
        "ENTRY_COMMITTEE",
        "PORTFOLIO_COMMITTEE",
        "EXIT_COMMITTEE",
    ]


def test_entry_is_independent_from_opportunity(payload):
    opportunity = get_committee(payload, "OPPORTUNITY_COMMITTEE")
    assert opportunity["entry_score_included_in_opportunity_quality"] is False


def test_entry_committee_is_timing_wall(payload):
    entry = get_committee(payload, "ENTRY_COMMITTEE")
    assert entry["minimum_entry_score"] == 70.0
    assert "DAILY_RSI_DIRECTION" in entry["timing_evidence"]
    assert "DAILY_STOCHASTIC_RSI_K_D_RELATIONSHIP" in entry["timing_evidence"]


def test_great_opportunity_with_bad_entry_is_rejected(payload):
    result = evaluate_trade_gate(
        payload,
        opportunity_quality_score=95.0,
        entry_score=45.0,
        thesis_intact=True,
    )
    assert result["opportunity_approved"] is True
    assert result["entry_approved"] is False
    assert result["eligible_for_portfolio_committee"] is False


def test_good_opportunity_and_good_entry_pass(payload):
    result = evaluate_trade_gate(
        payload,
        opportunity_quality_score=88.0,
        entry_score=82.0,
        thesis_intact=True,
    )
    assert result["eligible_for_portfolio_committee"] is True


def test_broken_thesis_blocks_entry(payload):
    result = evaluate_trade_gate(
        payload,
        opportunity_quality_score=90.0,
        entry_score=90.0,
        thesis_intact=False,
    )
    assert result["entry_approved"] is False


def test_sector_bias_is_forbidden(payload):
    assert payload["sector_bias_allowed"] is False
    portfolio = get_committee(payload, "PORTFOLIO_COMMITTEE")
    assert portfolio["sector_or_theme_adjustment_allowed"] is False


def test_theme_concentration_limit_is_forbidden(payload):
    assert payload["theme_concentration_limits_allowed"] is False
    portfolio = get_committee(payload, "PORTFOLIO_COMMITTEE")
    assert portfolio["theme_concentration_limits_allowed"] is False


def test_market_regime_is_not_a_hard_veto(payload):
    assert payload["market_regime_hard_veto_allowed"] is False
    entry = get_committee(payload, "ENTRY_COMMITTEE")
    assert entry["market_regime_hard_gate_allowed"] is False


def test_portfolio_allocation_is_rank_driven(payload):
    portfolio = get_committee(payload, "PORTFOLIO_COMMITTEE")
    assert portfolio["allocation_priority"] == "OPPORTUNITY_RANK_DESCENDING"
    assert portfolio["higher_rank_receives_more_capital"] is True
    assert portfolio["fixed_position_count_required"] is False


def test_exit_cannot_be_sector_or_regime_only(payload):
    exit_committee = get_committee(payload, "EXIT_COMMITTEE")
    assert exit_committee["sector_or_theme_exit_allowed"] is False
    assert exit_committee["market_regime_only_exit_allowed"] is False


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("paper_trade_mode", False),
        ("advisory_only", False),
        ("automatic_activation_allowed", True),
        ("sector_bias_allowed", True),
        ("theme_concentration_limits_allowed", True),
        ("market_regime_hard_veto_allowed", True),
        ("stock_history_bias_allowed", True),
    ],
)
def test_locked_top_level_policy_rejects_changes(payload, field, bad_value):
    changed = copy.deepcopy(payload)
    changed[field] = bad_value
    assert validate_committee_governance(changed).valid is False


def test_duplicate_committee_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["committees"][1]["committee_id"] = "DISCOVERY_COMMITTEE"
    result = validate_committee_governance(changed)
    assert result.valid is False
    assert any("Duplicate committee_id" in error for error in result.errors)


def test_out_of_order_committee_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["committees"][1], changed["committees"][2] = changed["committees"][2], changed["committees"][1]
    assert validate_committee_governance(changed).valid is False


def test_entry_blending_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["committees"][1]["entry_score_included_in_opportunity_quality"] = True
    assert validate_committee_governance(changed).valid is False


def test_missing_rsi_timing_evidence_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["committees"][2]["timing_evidence"].remove("DAILY_RSI_DIRECTION")
    assert validate_committee_governance(changed).valid is False


def test_sector_based_exit_rejected(payload):
    changed = copy.deepcopy(payload)
    changed["committees"][4]["sector_or_theme_exit_allowed"] = True
    assert validate_committee_governance(changed).valid is False


def test_summary(payload):
    summary = build_governance_summary(payload)
    assert summary["committee_count"] == 5
    assert summary["evidence_only_allocation"] is True
    assert summary["committee_ids"][-1] == "EXIT_COMMITTEE"


def test_write_governance(payload, tmp_path):
    output = write_committee_governance(payload, tmp_path / "results" / "governance.json")
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["plugin_id"] == "SWING-001"


def test_invalid_governance_is_not_written(payload, tmp_path):
    changed = copy.deepcopy(payload)
    changed["paper_trade_mode"] = False
    with pytest.raises(ValueError):
        write_committee_governance(changed, tmp_path / "governance.json")

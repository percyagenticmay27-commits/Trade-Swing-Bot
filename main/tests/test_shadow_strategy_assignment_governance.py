import json
from pathlib import Path

from swing_trade_bot.manual_entry_strategy_intake import apply_manual_entry_strategy_submission
from swing_trade_bot.manual_entry_strategy_registry import load_manual_entry_strategy_registry
from swing_trade_bot.shadow_strategy_promotion import promote_shadow_strategy
from swing_trade_bot.strategy_assignment_shadow_report import build_strategy_assignment_shadow_report


def _registry(path: Path) -> None:
    path.write_text(json.dumps({"schema_version": "1.4", "paper_trade_mode": True, "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR", "shadow_allocation_model": "SAME_CURRENT_SWING_ALLOCATION_SIMULATED_ONLY", "default_strategy_id": None, "strategies": [], "assignments": []}), encoding="utf-8")


def _submission(strategy_id: str, mode: str) -> dict:
    return {"strategy_id": strategy_id, "name": strategy_id.replace("_", " ").title(), "underlying_symbol": "NFLX", "assignment_mode": mode, "direction": "LONG", "timeframe": "1D", "session": "REGULAR_SESSION", "number_of_entries": 2, "rule_logic": "ALL", "rules": [{"left": "close", "operator": ">", "right": "ema", "period": 20}], "paper_trade_mode": True}


def test_one_direct_and_multiple_shadows_can_coexist(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"; form_path = tmp_path / "form.json"; _registry(registry_path)
    apply_manual_entry_strategy_submission(_submission("DIRECT_A", "DIRECT"), registry_path=registry_path, form_contract_path=form_path)
    apply_manual_entry_strategy_submission(_submission("SHADOW_B", "SHADOW"), registry_path=registry_path, form_contract_path=form_path)
    apply_manual_entry_strategy_submission(_submission("SHADOW_C", "SHADOW"), registry_path=registry_path, form_contract_path=form_path)
    registry = load_manual_entry_strategy_registry(registry_path)
    assert registry.resolve("NFLX").strategy_id == "DIRECT_A"
    assert [item.strategy_id for item in registry.shadow_strategies("NFLX")] == ["SHADOW_B", "SHADOW_C"]
    assert len(registry.assignments) == 3


def test_saving_new_direct_demotes_old_direct_and_preserves_existing_shadows(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"; form_path = tmp_path / "form.json"; _registry(registry_path)
    for sid, mode in (("DIRECT_A", "DIRECT"), ("SHADOW_B", "SHADOW"), ("DIRECT_D", "DIRECT")):
        apply_manual_entry_strategy_submission(_submission(sid, mode), registry_path=registry_path, form_contract_path=form_path)
    registry = load_manual_entry_strategy_registry(registry_path)
    assert registry.resolve("NFLX").strategy_id == "DIRECT_D"
    assert {item.strategy_id for item in registry.shadow_strategies("NFLX")} == {"DIRECT_A", "SHADOW_B"}
    assert len([item for item in registry.assignments if item.underlying_symbol == "NFLX" and item.assignment_mode == "DIRECT"]) == 1


def test_shadow_report_uses_same_current_swing_allocation_and_veto_governance(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"; form_path = tmp_path / "form.json"; allocation_path = tmp_path / "alloc.json"; performance_path = tmp_path / "shadow.json"; _registry(registry_path)
    apply_manual_entry_strategy_submission(_submission("DIRECT_A", "DIRECT"), registry_path=registry_path, form_contract_path=form_path)
    apply_manual_entry_strategy_submission(_submission("SHADOW_B", "SHADOW"), registry_path=registry_path, form_contract_path=form_path)
    allocation_path.write_text(json.dumps({"allocations": [{"underlying_symbol": "NFLX", "allocated_capital": 600.0}]}), encoding="utf-8")
    performance_path.write_text(json.dumps({"rows": [{"underlying_symbol": "NFLX", "strategy_id": "SHADOW_B", "trade_count": 8, "win_rate": 62.5, "net_pl": 75.0, "max_drawdown": -18.0, "profit_factor": 2.1, "promotion_recommended": True}]}), encoding="utf-8")
    report = build_strategy_assignment_shadow_report(registry_path=registry_path, allocation_path=allocation_path, shadow_performance_path=performance_path)
    row = report["rows"][0]; shadow = row["shadow_strategies"][0]
    assert row["direct_strategy_id"] == "DIRECT_A"
    assert shadow["simulated_allocation"] == 600.0
    assert shadow["net_pl"] == 75.0
    assert shadow["max_drawdown"] == -18.0
    assert shadow["promotion_recommended"] is True
    assert shadow["promotion_requires_affirmative_approval"] is False
    assert shadow["user_veto_allowed"] is True
    assert report["shadow_capital_reserved"] is False
    assert report["shadow_capital_movement_enabled"] is False
    assert report["auto_promotion_enabled"] is True
    assert report["affirmative_approval_required"] is False
    assert report["promotion_authority"] == "AUTOMATIC_AFTER_QUALIFICATION_AND_VETO_WINDOW"


def test_promotion_without_affirmative_approval_promotes_shadow_and_retains_old_direct(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"; form_path = tmp_path / "form.json"; report_path = tmp_path / "assignment_report.json"; _registry(registry_path)
    apply_manual_entry_strategy_submission(_submission("DIRECT_A", "DIRECT"), registry_path=registry_path, form_contract_path=form_path)
    apply_manual_entry_strategy_submission(_submission("SHADOW_B", "SHADOW"), registry_path=registry_path, form_contract_path=form_path)
    result = promote_shadow_strategy(underlying_symbol="NFLX", strategy_id="SHADOW_B", registry_path=registry_path, form_contract_path=form_path, assignment_report_path=report_path)
    registry = load_manual_entry_strategy_registry(registry_path)
    assert result.status == "PROMOTED"
    assert result.user_vetoed is False
    assert result.previous_direct_strategy_id == "DIRECT_A"
    assert registry.resolve("NFLX").strategy_id == "SHADOW_B"
    assert [item.strategy_id for item in registry.shadow_strategies("NFLX")] == ["DIRECT_A"]
    assert report_path.is_file()


def test_explicit_veto_blocks_promotion_without_mutating_assignments(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"; form_path = tmp_path / "form.json"; report_path = tmp_path / "assignment_report.json"; _registry(registry_path)
    apply_manual_entry_strategy_submission(_submission("DIRECT_A", "DIRECT"), registry_path=registry_path, form_contract_path=form_path)
    apply_manual_entry_strategy_submission(_submission("SHADOW_B", "SHADOW"), registry_path=registry_path, form_contract_path=form_path)
    result = promote_shadow_strategy(underlying_symbol="NFLX", strategy_id="SHADOW_B", user_vetoed=True, registry_path=registry_path, form_contract_path=form_path, assignment_report_path=report_path)
    registry = load_manual_entry_strategy_registry(registry_path)
    assert result.status == "VETOED"
    assert result.user_vetoed is True
    assert registry.resolve("NFLX").strategy_id == "DIRECT_A"
    assert [item.strategy_id for item in registry.shadow_strategies("NFLX")] == ["SHADOW_B"]
    assert not report_path.exists()

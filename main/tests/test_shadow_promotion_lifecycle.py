from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.manual_entry_strategy_intake import apply_manual_entry_strategy_submission
from swing_trade_bot.manual_entry_strategy_registry import load_manual_entry_strategy_registry
from swing_trade_bot.shadow_promotion_lifecycle import (
    PENDING_VETO,
    PROMOTED,
    VETOED,
    load_promotion_lifecycle,
    process_pending_promotions,
    queue_qualified_shadow,
)
from swing_trade_bot.user_veto_control import append_veto_event


def _registry(path: Path) -> None:
    path.write_text(json.dumps({"schema_version": "1.4", "paper_trade_mode": True, "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR", "shadow_allocation_model": "SAME_CURRENT_SWING_ALLOCATION_SIMULATED_ONLY", "default_strategy_id": None, "strategies": [], "assignments": []}), encoding="utf-8")


def _submission(strategy_id: str, mode: str) -> dict:
    return {"strategy_id": strategy_id, "name": strategy_id.replace("_", " ").title(), "underlying_symbol": "NFLX", "assignment_mode": mode, "direction": "LONG", "timeframe": "1D", "session": "REGULAR_SESSION", "number_of_entries": 2, "rule_logic": "ALL", "rules": [{"left": "close", "operator": ">", "right": "ema", "period": 20}], "paper_trade_mode": True}


def _setup(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    report_path = tmp_path / "assignment_report.json"
    lifecycle_path = tmp_path / "promotion_lifecycle.json"
    veto_path = tmp_path / "user_veto_ledger.json"
    _registry(registry_path)
    apply_manual_entry_strategy_submission(_submission("DIRECT_A", "DIRECT"), registry_path=registry_path, form_contract_path=form_path)
    apply_manual_entry_strategy_submission(_submission("SHADOW_B", "SHADOW"), registry_path=registry_path, form_contract_path=form_path)
    return registry_path, form_path, report_path, lifecycle_path, veto_path


def test_qualified_shadow_enters_pending_veto_without_changing_primary(tmp_path: Path) -> None:
    registry_path, form_path, _, lifecycle_path, _ = _setup(tmp_path)
    event = queue_qualified_shadow(
        underlying_symbol="NFLX",
        strategy_id="SHADOW_B",
        qualified_at="2026-09-02T12:00:00Z",
        veto_deadline="2026-09-03T12:00:00Z",
        lifecycle_path=lifecycle_path,
        qualification_evidence={"trade_count": 24, "months_outperforming": 3},
    )
    assert event.status == PENDING_VETO
    assert load_manual_entry_strategy_registry(registry_path).resolve("NFLX").strategy_id == "DIRECT_A"
    payload = load_promotion_lifecycle(lifecycle_path)
    assert payload["affirmative_approval_required"] is False
    assert payload["user_veto_allowed"] is True
    assert payload["events"][0]["qualification_evidence"]["months_outperforming"] == 3


def test_before_veto_deadline_nothing_is_promoted(tmp_path: Path) -> None:
    registry_path, form_path, report_path, lifecycle_path, veto_path = _setup(tmp_path)
    queue_qualified_shadow(underlying_symbol="NFLX", strategy_id="SHADOW_B", qualified_at="2026-09-02T12:00:00Z", veto_deadline="2026-09-03T12:00:00Z", lifecycle_path=lifecycle_path)
    resolved = process_pending_promotions(
        now="2026-09-03T11:59:59Z",
        lifecycle_path=lifecycle_path,
        veto_ledger_path=veto_path,
        registry_path=registry_path,
        form_contract_path=form_path,
        assignment_report_path=report_path,
    )
    assert resolved == ()
    assert load_manual_entry_strategy_registry(registry_path).resolve("NFLX").strategy_id == "DIRECT_A"
    assert load_promotion_lifecycle(lifecycle_path)["events"][0]["status"] == PENDING_VETO


def test_active_user_veto_blocks_expired_pending_promotion(tmp_path: Path) -> None:
    registry_path, form_path, report_path, lifecycle_path, veto_path = _setup(tmp_path)
    queue_qualified_shadow(underlying_symbol="NFLX", strategy_id="SHADOW_B", qualified_at="2026-09-02T12:00:00Z", veto_deadline="2026-09-03T12:00:00Z", lifecycle_path=lifecycle_path)
    append_veto_event(veto_path, symbol="NFLX", action="VETO", rationale="Keep current Primary", timestamp="2026-09-03T10:00:00Z")
    resolved = process_pending_promotions(
        now="2026-09-03T12:00:01Z",
        lifecycle_path=lifecycle_path,
        veto_ledger_path=veto_path,
        registry_path=registry_path,
        form_contract_path=form_path,
        assignment_report_path=report_path,
    )
    assert len(resolved) == 1
    assert resolved[0].status == VETOED
    registry = load_manual_entry_strategy_registry(registry_path)
    assert registry.resolve("NFLX").strategy_id == "DIRECT_A"
    assert [item.strategy_id for item in registry.shadow_strategies("NFLX")] == ["SHADOW_B"]


def test_no_veto_after_deadline_auto_promotes_and_demotes_old_primary(tmp_path: Path) -> None:
    registry_path, form_path, report_path, lifecycle_path, veto_path = _setup(tmp_path)
    queue_qualified_shadow(underlying_symbol="NFLX", strategy_id="SHADOW_B", qualified_at="2026-09-02T12:00:00Z", veto_deadline="2026-09-03T12:00:00Z", lifecycle_path=lifecycle_path)
    resolved = process_pending_promotions(
        now="2026-09-03T12:00:01Z",
        lifecycle_path=lifecycle_path,
        veto_ledger_path=veto_path,
        registry_path=registry_path,
        form_contract_path=form_path,
        assignment_report_path=report_path,
    )
    assert len(resolved) == 1
    assert resolved[0].status == PROMOTED
    assert resolved[0].previous_direct_strategy_id == "DIRECT_A"
    registry = load_manual_entry_strategy_registry(registry_path)
    assert registry.resolve("NFLX").strategy_id == "SHADOW_B"
    assert [item.strategy_id for item in registry.shadow_strategies("NFLX")] == ["DIRECT_A"]
    assert load_promotion_lifecycle(lifecycle_path)["events"][0]["status"] == PROMOTED


def test_duplicate_pending_event_is_not_created(tmp_path: Path) -> None:
    _, _, _, lifecycle_path, _ = _setup(tmp_path)
    for _ in range(2):
        queue_qualified_shadow(underlying_symbol="NFLX", strategy_id="SHADOW_B", qualified_at="2026-09-02T12:00:00Z", veto_deadline="2026-09-03T12:00:00Z", lifecycle_path=lifecycle_path)
    assert len(load_promotion_lifecycle(lifecycle_path)["events"]) == 1

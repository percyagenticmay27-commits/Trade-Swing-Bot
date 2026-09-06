import json
from pathlib import Path

from swing_trade_bot.frozen_strategy_assignment_registry import load_frozen_symbol_stacks, promote_frozen_shadow
from swing_trade_bot.frozen_strategy_promotion_workflow import (
    AFFIRMATIVE_APPROVAL_REQUIRED,
    AUTO_PROMOTION_AFTER_VETO_DEADLINE,
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    build_frozen_monthly_promotion_review,
    process_frozen_pending_promotions,
)
from swing_trade_bot.user_veto_control import append_veto_event


def _config(path: Path) -> None:
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "paper_trade_mode": True,
        "strategy_id": "SWING-001",
        "symbols": [{
            "symbol": "SOXL",
            "research_status": "FROZEN_DEPLOYMENT_STACK",
            "primary_strategy_id": "PRIMARY_A",
            "shadow_strategy_ids": ["SHADOW_B", "SHADOW_C"],
            "shadow_slot_3": None,
        }],
        "strategies": [
            {
                "strategy_id": "PRIMARY_A", "name": "Primary A", "signal_symbol": "SOXL", "vehicle_symbol": "SOXL",
                "timeframe": "1H", "engine_id": "BIGBELUGA_RANGE", "parameters": {"hma_exit": 90},
                "catastrophic_stop_percent": 20, "assignment_mode": "DIRECT", "enabled": True, "paper_trade_mode": True,
            },
            {
                "strategy_id": "SHADOW_B", "name": "Shadow B", "signal_symbol": "SOXL", "vehicle_symbol": "SOXL",
                "timeframe": "1H", "engine_id": "ZERO_LAG", "parameters": {"length": 70, "multiplier": 2.5},
                "catastrophic_stop_percent": 20, "assignment_mode": "SHADOW", "enabled": True, "paper_trade_mode": True,
            },
            {
                "strategy_id": "SHADOW_C", "name": "Shadow C", "signal_symbol": "SOXL", "vehicle_symbol": "SOXL",
                "timeframe": "4H", "engine_id": "ZERO_LAG", "parameters": {"length": 20, "multiplier": 1.0},
                "catastrophic_stop_percent": 20, "assignment_mode": "SHADOW", "enabled": True, "paper_trade_mode": True,
            },
        ],
    }), encoding="utf-8")


def _performance(path: Path, *, mismatch: bool = False) -> None:
    rows = [
        {
            "underlying_symbol": "SOXL", "strategy_id": "PRIMARY_A", "assignment_mode": "DIRECT", "evidence_status": "AVAILABLE",
            "net_pl": 100.0, "gross_profit": 150.0, "gross_loss": -50.0, "profit_factor": 3.0,
            "max_drawdown": -40.0, "trade_count": 40, "sizing_basis": "PRIMARY_SHARE_QUANTITY",
            "primary_reference_quantity": 8.0, "shadow_test_quantity": 8.0,
        },
        {
            "underlying_symbol": "SOXL", "strategy_id": "SHADOW_B", "assignment_mode": "SHADOW", "evidence_status": "AVAILABLE",
            "net_pl": 150.0, "gross_profit": 200.0, "gross_loss": -50.0, "profit_factor": 4.0,
            "max_drawdown": -45.0, "trade_count": 45, "sizing_basis": "PRIMARY_SHARE_QUANTITY",
            "primary_reference_quantity": 8.0, "shadow_test_quantity": 9.0 if mismatch else 8.0,
        },
        {
            "underlying_symbol": "SOXL", "strategy_id": "SHADOW_C", "assignment_mode": "SHADOW", "evidence_status": "AVAILABLE",
            "net_pl": 80.0, "gross_profit": 120.0, "gross_loss": -40.0, "profit_factor": 3.0,
            "max_drawdown": -30.0, "trade_count": 35, "sizing_basis": "PRIMARY_SHARE_QUANTITY",
            "primary_reference_quantity": 8.0, "shadow_test_quantity": 8.0,
        },
    ]
    path.write_text(json.dumps({"schema_version": "1.0", "strategy_id": "SWING-001", "paper_trade_mode": True, "rows": rows}), encoding="utf-8")


def _allocation(path: Path) -> None:
    path.write_text(json.dumps({"allocations": [{"underlying_symbol": "SOXL", "vehicle_symbol": "SOXL", "allocated_capital": 1000.0}]}), encoding="utf-8")


def test_promote_frozen_shadow_swaps_authority_and_preserves_shadow_slot(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    _config(config)
    previous = promote_frozen_shadow(symbol="SOXL", strategy_id="SHADOW_B", path=config)
    assert previous == "PRIMARY_A"
    stack = load_frozen_symbol_stacks(config)[0]
    assert stack.primary.strategy_id == "SHADOW_B"
    assert [item.strategy_id for item in stack.shadows] == ["PRIMARY_A", "SHADOW_C"]
    assert stack.primary.assignment_mode == "DIRECT"
    assert all(item.assignment_mode == "SHADOW" for item in stack.shadows)


def test_three_monthly_reviews_queue_then_auto_promote_after_veto_deadline(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    performance = tmp_path / "performance.json"
    allocation = tmp_path / "allocation.json"
    state = tmp_path / "state.json"
    report = tmp_path / "report.json"
    history = tmp_path / "history.json"
    lifecycle = tmp_path / "lifecycle.json"
    veto = tmp_path / "veto.json"
    _config(config)
    _performance(performance)
    _allocation(allocation)

    for stamp in ("2026-09-02T17:00:00Z", "2026-10-02T17:00:00Z", "2026-11-02T17:00:00Z"):
        result = build_frozen_monthly_promotion_review(
            now=stamp, veto_window_days=3, config_path=config, performance_path=performance,
            allocation_path=allocation, monthly_state_path=state, review_report_path=report,
            review_history_path=history, lifecycle_path=lifecycle,
        )
    assert result["rows"][0]["status"] == "QUALIFIED_PENDING_VETO"
    assert result["rows"][0]["qualified_strategy_id"] == "SHADOW_B"

    before = load_frozen_symbol_stacks(config)[0]
    assert before.primary.strategy_id == "PRIMARY_A"
    resolved = process_frozen_pending_promotions(
        now="2026-11-06T17:00:00Z", config_path=config, lifecycle_path=lifecycle, veto_ledger_path=veto,
    )
    assert len(resolved) == 1
    assert resolved[0].status == "PROMOTED"
    assert resolved[0].previous_direct_strategy_id == "PRIMARY_A"
    after = load_frozen_symbol_stacks(config)[0]
    assert after.primary.strategy_id == "SHADOW_B"
    assert [item.strategy_id for item in after.shadows] == ["PRIMARY_A", "SHADOW_C"]


def test_active_user_veto_blocks_frozen_auto_promotion(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    lifecycle = tmp_path / "lifecycle.json"
    veto = tmp_path / "veto.json"
    _config(config)
    lifecycle.write_text(json.dumps({
        "schema_version": "1.0", "strategy_id": "SWING-001", "paper_trade_mode": True,
        "affirmative_approval_required": False, "user_veto_allowed": True,
        "events": [{
            "underlying_symbol": "SOXL", "strategy_id": "SHADOW_B", "status": "PENDING_VETO",
            "qualified_at": "2026-11-02T17:00:00Z", "veto_deadline": "2026-11-05T17:00:00Z",
            "resolved_at": None, "previous_direct_strategy_id": None, "qualification_evidence": {}, "paper_trade_mode": True,
        }],
    }), encoding="utf-8")
    append_veto_event(veto, symbol="SOXL", action="VETO", timestamp="2026-11-04T17:00:00Z")
    resolved = process_frozen_pending_promotions(
        now="2026-11-06T17:00:00Z", config_path=config, lifecycle_path=lifecycle, veto_ledger_path=veto,
    )
    assert resolved[0].status == "VETOED"
    assert load_frozen_symbol_stacks(config)[0].primary.strategy_id == "PRIMARY_A"


def test_quantity_mismatch_does_not_consume_monthly_review(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    performance = tmp_path / "performance.json"
    allocation = tmp_path / "allocation.json"
    state = tmp_path / "state.json"
    _config(config)
    _performance(performance, mismatch=True)
    _allocation(allocation)
    result = build_frozen_monthly_promotion_review(
        now="2026-09-02T17:00:00Z", veto_window_days=3, config_path=config, performance_path=performance,
        allocation_path=allocation, monthly_state_path=state, review_report_path=tmp_path / "report.json",
        review_history_path=tmp_path / "history.json", lifecycle_path=tmp_path / "lifecycle.json",
    )
    assert result["rows"][0]["status"] == "SHADOW_QUANTITY_MISMATCH"
    assert not state.exists()


def test_frozen_promotion_governance_remains_paper_only() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert AFFIRMATIVE_APPROVAL_REQUIRED is False
    assert AUTO_PROMOTION_AFTER_VETO_DEADLINE is True

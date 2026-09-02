import json
from pathlib import Path

import swing_trade_bot.frozen_primary_signal_execution_workflow as workflow


PRIMARY = "SOXL_BIGBELUGA_1H_PRIMARY"
SHADOW = "SOXL_ZERO_LAG_1H_SHADOW_1"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _config(path: Path, *, primary: str = PRIMARY) -> None:
    strategies = [
        {
            "strategy_id": PRIMARY,
            "name": "Primary",
            "signal_symbol": "SOXL",
            "vehicle_symbol": "SOXL",
            "timeframe": "1H",
            "engine_id": "BIGBELUGA_RANGE",
            "parameters": {"hma_entry": 0, "hma_exit": 90, "chop_max": 0.0, "atr_pct_min": 0.0},
            "catastrophic_stop_percent": 20.0,
            "assignment_mode": "DIRECT" if primary == PRIMARY else "SHADOW",
            "enabled": True,
            "paper_trade_mode": True,
        },
        {
            "strategy_id": SHADOW,
            "name": "Shadow",
            "signal_symbol": "SOXL",
            "vehicle_symbol": "SOXL",
            "timeframe": "1H",
            "engine_id": "ZERO_LAG",
            "parameters": {"length": 70, "multiplier": 2.5, "adx_min": 0.0, "chop_max": 55.0, "atr_pct_min": 0.0},
            "catastrophic_stop_percent": 20.0,
            "assignment_mode": "DIRECT" if primary == SHADOW else "SHADOW",
            "enabled": True,
            "paper_trade_mode": True,
        },
    ]
    other = SHADOW if primary == PRIMARY else PRIMARY
    _write_json(path, {
        "schema_version": "1.0",
        "paper_trade_mode": True,
        "strategy_id": "SWING-001",
        "symbols": [{
            "symbol": "SOXL",
            "primary_strategy_id": primary,
            "shadow_strategy_ids": [other],
            "shadow_slot_3": None,
            "research_status": "TEST",
        }],
        "strategies": strategies,
    })


def _ledger(path: Path, *, open_position: bool = True) -> None:
    position = {
        "symbol": "SOXL",
        "opened_at": "2026-09-01T13:30:00-04:00",
        "entry_date": "2026-09-01",
        "entry_price": 100.0,
        "shares": 10.0,
        "cost_basis": 1000.0,
        "current_price": 100.0,
        "market_value": 1000.0,
        "unrealized_pnl": 0.0,
        "unrealized_pnl_percent": 0.0,
        "allocation_percent": 0.0,
        "active_strategy": PRIMARY,
        "status": "OPEN",
    }
    _write_json(path / "open_positions.json", {
        "paper_trade_mode": True,
        "positions": [position] if open_position else [],
    })
    _write_json(path / "trade_history.json", {
        "paper_trade_mode": True,
        "trades": [],
    })


def _intraday(path: Path, *, hours: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["Timestamp,Open,High,Low,Close,Volume"]
    # One row per hour is enough for deterministic chart buckets in these tests.
    for i in range(hours):
        hour = 9 + ((30 + i * 60) // 60)
        minute = (30 + i * 60) % 60
        price = 100 + i
        rows.append(f"2026-09-01T{hour:02d}:{minute:02d}:00-04:00,{price},{price+1},{price-1},{price+0.5},1000")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _paths(tmp_path: Path):
    config = tmp_path / "frozen.json"
    intraday = tmp_path / "intraday"
    ledger = tmp_path / "ledger"
    state = tmp_path / "state.json"
    report = tmp_path / "report.json"
    return config, intraday, ledger, state, report


def test_first_run_initializes_nonretroactive_baseline_without_trade(tmp_path):
    config, intraday, ledger, state, report = _paths(tmp_path)
    _config(config)
    _ledger(ledger)
    _intraday(intraday / "SOXL.csv", hours=3)

    result = workflow.run_frozen_primary_signal_execution(
        config_path=config, intraday_dir=intraday, ledger_dir=ledger,
        state_path=state, report_path=report,
    )

    assert result["rows"][0]["status"] == "BASELINE_INITIALIZED"
    assert result["rows"][0]["executed_events"] == []
    assert json.loads((ledger / "trade_history.json").read_text())["trades"] == []
    saved = json.loads(state.read_text())
    assert saved["symbols"]["SOXL"]["allocation_notional"] == 1000.0
    assert saved["symbols"]["SOXL"]["strategy_id"] == PRIMARY


def test_pending_exit_executes_at_next_chart_bar_open(tmp_path):
    config, intraday, ledger, state, report = _paths(tmp_path)
    _config(config)
    _ledger(ledger)
    _intraday(intraday / "SOXL.csv", hours=3)
    _write_json(state, {
        "paper_trade_mode": True,
        "symbols": {"SOXL": {
            "strategy_id": PRIMARY,
            "last_processed_chart_bar": "2026-09-01T09:30:00-04:00",
            "pending_signal": {
                "side": "SELL",
                "signal_chart_bar": "2026-09-01T09:30:00-04:00",
                "reason": "TEST_PENDING_EXIT",
            },
            "allocation_notional": 1000.0,
        }},
    })

    class Decision:
        entry_signal = False
        exit_signal = False

    original = workflow.evaluate_frozen_signal
    workflow.evaluate_frozen_signal = lambda *args, **kwargs: Decision()
    try:
        result = workflow.run_frozen_primary_signal_execution(
            config_path=config, intraday_dir=intraday, ledger_dir=ledger,
            state_path=state, report_path=report,
        )
    finally:
        workflow.evaluate_frozen_signal = original

    event = result["rows"][0]["executed_events"][0]
    assert event["side"] == "SELL"
    assert event["price"] == 101.0
    assert event["shares"] == 10.0
    assert json.loads((ledger / "open_positions.json").read_text())["positions"] == []


def test_confirmed_entry_uses_preserved_allocation_notional_on_next_bar_open(tmp_path):
    config, intraday, ledger, state, report = _paths(tmp_path)
    _config(config)
    _ledger(ledger, open_position=False)
    _intraday(intraday / "SOXL.csv", hours=3)
    _write_json(state, {
        "paper_trade_mode": True,
        "symbols": {"SOXL": {
            "strategy_id": PRIMARY,
            "last_processed_chart_bar": "2026-09-01T09:30:00-04:00",
            "pending_signal": None,
            "allocation_notional": 1000.0,
        }},
    })

    calls = {"count": 0}
    class Decision:
        def __init__(self, entry=False, exit=False):
            self.entry_signal = entry
            self.exit_signal = exit

    original = workflow.evaluate_frozen_signal
    def fake(*args, **kwargs):
        calls["count"] += 1
        return Decision(entry=(calls["count"] == 1))
    workflow.evaluate_frozen_signal = fake
    try:
        result = workflow.run_frozen_primary_signal_execution(
            config_path=config, intraday_dir=intraday, ledger_dir=ledger,
            state_path=state, report_path=report,
        )
    finally:
        workflow.evaluate_frozen_signal = original

    event = result["rows"][0]["executed_events"][0]
    assert event["side"] == "BUY"
    assert event["price"] == 102.0
    assert event["notional"] == 1000.0
    position = json.loads((ledger / "open_positions.json").read_text())["positions"][0]
    assert position["active_strategy"] == PRIMARY
    assert position["cost_basis"] == 1000.0


def test_primary_promotion_rebaselines_without_replaying_new_strategy_history(tmp_path):
    config, intraday, ledger, state, report = _paths(tmp_path)
    _config(config, primary=SHADOW)
    _ledger(ledger)
    # Simulate the already-promoted strategy controlling the existing position.
    payload = json.loads((ledger / "open_positions.json").read_text())
    payload["positions"][0]["active_strategy"] = SHADOW
    _write_json(ledger / "open_positions.json", payload)
    _intraday(intraday / "SOXL.csv", hours=3)
    _write_json(state, {
        "paper_trade_mode": True,
        "symbols": {"SOXL": {
            "strategy_id": PRIMARY,
            "last_processed_chart_bar": "2026-09-01T09:30:00-04:00",
            "pending_signal": None,
            "allocation_notional": 1000.0,
        }},
    })

    result = workflow.run_frozen_primary_signal_execution(
        config_path=config, intraday_dir=intraday, ledger_dir=ledger,
        state_path=state, report_path=report,
    )
    assert result["rows"][0]["status"] == "PRIMARY_CHANGE_REBASELINED"
    assert result["rows"][0]["executed_events"] == []
    saved = json.loads(state.read_text())
    assert saved["symbols"]["SOXL"]["strategy_id"] == SHADOW


def test_workflow_never_executes_shadow_assignments_and_safety_is_locked(tmp_path):
    config, intraday, ledger, state, report = _paths(tmp_path)
    _config(config)
    _ledger(ledger)
    _intraday(intraday / "SOXL.csv", hours=2)

    result = workflow.run_frozen_primary_signal_execution(
        config_path=config, intraday_dir=intraday, ledger_dir=ledger,
        state_path=state, report_path=report,
    )
    assert result["execution_scope"] == "FROZEN_DIRECT_PRIMARY_ONLY"
    assert result["shadow_execution_enabled"] is False
    assert result["paper_trade_mode"] is True
    assert result["live_trading_enabled"] is False
    assert result["broker_execution_enabled"] is False
    assert result["order_placement_enabled"] is False
    assert result["capital_movement_enabled"] is False
    assert all(row["strategy_id"] != SHADOW for row in result["rows"])

import csv
import json
from pathlib import Path

from swing_trade_bot.paper_ledger_foundation import SWING_ALLOCATION, initialize_paper_ledger


def test_initializes_empty_authoritative_ledger(tmp_path):
    ledger = tmp_path / "paper_ledger"
    status = initialize_paper_ledger(ledger)

    assert status["status"] == "READY"
    assert status["allocated_capital"] == 4500.0
    assert SWING_ALLOCATION == 4500.0
    assert json.loads((ledger / "open_positions.json").read_text())["positions"] == []
    assert json.loads((ledger / "trade_history.json").read_text())["trades"] == []
    assert json.loads((ledger / "managed_trade_history.json").read_text())["trades"] == []
    assert (ledger / "paper_portfolio_positions.csv").exists()
    assert (ledger / "paper_performance.csv").exists()
    assert (ledger / "paper_ledger_status.json").exists()


def test_preserves_existing_positions_and_projects_csv(tmp_path):
    ledger = tmp_path / "paper_ledger"
    ledger.mkdir()
    position = {
        "symbol": "SOXL", "status": "OPEN", "entry_date": "2026-08-04",
        "entry_price": 100.0, "shares": 10.0, "cost_basis": 1000.0,
        "current_price": 140.0, "market_value": 1400.0,
        "unrealized_pnl": 400.0, "unrealized_pnl_percent": 40.0,
        "allocation_percent": 22.2222, "active_strategy": "Strategy A",
    }
    (ledger / "open_positions.json").write_text(json.dumps({"positions": [position]}))
    (ledger / "trade_history.json").write_text(json.dumps({"trades": [{"trade_id": "PAPER-SOXL-BUY"}]}))

    status = initialize_paper_ledger(ledger)

    assert status["position_count"] == 1
    assert status["trade_count"] == 1
    assert json.loads((ledger / "open_positions.json").read_text())["positions"][0]["entry_price"] == 100.0
    with (ledger / "paper_portfolio_positions.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["symbol"] == "SOXL"
    assert rows[0]["current_price"] == "140.0"


def test_rerun_is_idempotent_and_does_not_invent_positions(tmp_path):
    ledger = tmp_path / "paper_ledger"
    first = initialize_paper_ledger(ledger)
    second = initialize_paper_ledger(ledger)
    assert first["position_count"] == second["position_count"] == 0
    assert json.loads((ledger / "open_positions.json").read_text())["positions"] == []


def test_paper_only_safety_flags_are_locked(tmp_path):
    status = initialize_paper_ledger(tmp_path / "paper_ledger")
    assert status["paper_trade_mode"] is True
    assert status["live_trading_enabled"] is False
    assert status["broker_execution_enabled"] is False
    assert status["order_placement_enabled"] is False
    assert status["capital_movement_enabled"] is False

import csv
import json
from datetime import date
from pathlib import Path

import swing_trade_bot.frozen_primary_post_execution_refresh as refresh


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_daily(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2026-09-01,100,101,99,100,100,1000\n"
        "2026-09-02,105,106,104,105,105,1000\n",
        encoding="utf-8",
    )


def _cycle_config(path: Path) -> None:
    _write_json(path, {
        "runtime_evidence_refresh": {
            "enabled": True,
            "paper_ledger": {
                "ledger_dir": "ledger",
                "data_dir": "data",
                "max_price_age_days": 5,
            },
        },
    })


def _allocation_mocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        refresh,
        "load_discovered_strategy_allocations",
        lambda: ({"allocations": []}, tmp_path / "allocation.json"),
    )
    monkeypatch.setattr(
        refresh,
        "resolve_strategy_allocation_evidence",
        lambda payload, strategy_id: {
            "allocated_capital": 4500.0,
            "allocation_source_json_path": "$.strategies.SWING-001",
            "allocation_evidence_schema": "TEST",
        },
    )


def test_refresh_rebuilds_current_positions_trade_history_and_performance(tmp_path, monkeypatch):
    _cycle_config(tmp_path / "cycle.json")
    _allocation_mocks(monkeypatch, tmp_path)
    _write_daily(tmp_path / "data" / "SOXL.csv")
    _write_json(tmp_path / "ledger" / "open_positions.json", {
        "paper_trade_mode": True,
        "positions": [{
            "symbol": "SOXL",
            "entry_date": "2026-09-01",
            "entry_price": 100.0,
            "shares": 10.0,
            "cost_basis": 1000.0,
            "allocation_percent": 22.22,
            "active_strategy": "SOXL_BIGBELUGA_1H_PRIMARY",
        }],
    })
    _write_json(tmp_path / "ledger" / "trade_history.json", {
        "paper_trade_mode": True,
        "trades": [{
            "trade_id": "BUY-1",
            "symbol": "SOXL",
            "side": "BUY",
            "trade_date": "2026-09-01",
            "price": 100.0,
            "shares": 10.0,
            "notional": 1000.0,
            "active_strategy": "SOXL_BIGBELUGA_1H_PRIMARY",
            "reason": "TEST",
            "paper_trade_mode": True,
        }],
    })

    result = refresh.refresh_frozen_primary_post_execution_evidence(
        cycle_config_path=Path("cycle.json"),
        repository_root=tmp_path,
        as_of=date(2026, 9, 2),
    )

    assert result["position_count"] == 1
    assert result["closed_trade_count"] == 0
    assert result["total_pnl"] == 50.0
    current = list(csv.DictReader((tmp_path / "ledger" / "current_portfolio_positions.csv").open()))
    assert current[0]["symbol"] == "SOXL"
    assert float(current[0]["shares"]) == 10.0
    assert (tmp_path / "ledger" / "trade_history_summary.json").is_file()
    assert (tmp_path / "ledger" / "paper_performance.json").is_file()


def test_refresh_after_sell_reports_realized_pnl_and_empty_current_positions(tmp_path, monkeypatch):
    _cycle_config(tmp_path / "cycle.json")
    _allocation_mocks(monkeypatch, tmp_path)
    _write_daily(tmp_path / "data" / "SOXL.csv")
    _write_json(tmp_path / "ledger" / "open_positions.json", {
        "paper_trade_mode": True,
        "positions": [],
    })
    _write_json(tmp_path / "ledger" / "trade_history.json", {
        "paper_trade_mode": True,
        "trades": [
            {
                "trade_id": "BUY-1", "symbol": "SOXL", "side": "BUY",
                "trade_date": "2026-09-01", "price": 100.0, "shares": 10.0,
                "notional": 1000.0, "active_strategy": "SOXL_BIGBELUGA_1H_PRIMARY",
                "reason": "TEST", "paper_trade_mode": True,
            },
            {
                "trade_id": "SELL-1", "symbol": "SOXL", "side": "SELL",
                "trade_date": "2026-09-02", "price": 105.0, "shares": 10.0,
                "notional": 1050.0, "active_strategy": "SOXL_BIGBELUGA_1H_PRIMARY",
                "reason": "TEST", "paper_trade_mode": True,
            },
        ],
    })

    result = refresh.refresh_frozen_primary_post_execution_evidence(
        cycle_config_path=Path("cycle.json"),
        repository_root=tmp_path,
        as_of=date(2026, 9, 2),
    )

    assert result["position_count"] == 0
    assert result["closed_trade_count"] == 1
    assert result["total_pnl"] == 50.0
    rows = list(csv.DictReader((tmp_path / "ledger" / "current_portfolio_positions.csv").open()))
    assert rows == []


def test_safety_flags_are_locked():
    assert refresh.PAPER_TRADE_MODE is True
    assert refresh.LIVE_TRADING_ENABLED is False
    assert refresh.BROKER_EXECUTION_ENABLED is False
    assert refresh.ORDER_PLACEMENT_ENABLED is False
    assert refresh.CAPITAL_MOVEMENT_ENABLED is False

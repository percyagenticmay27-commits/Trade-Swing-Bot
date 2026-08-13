from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from swing_trade_bot import swing_daily_cycle as cycle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_current_portfolio_adapter_uses_only_authoritative_paper_positions(tmp_path: Path) -> None:
    source = tmp_path / "paper_portfolio_positions.json"
    destination = tmp_path / "current_portfolio_positions.csv"
    _write_json(
        source,
        {
            "paper_trade_mode": True,
            "position_count": 2,
            "positions": [
                {
                    "symbol": "SOXL",
                    "shares": 8.04145854,
                    "market_value": 1200.0,
                    "cost_basis": 1125.0,
                    "current_price": 149.22,
                    "unrealized_pnl": 75.0,
                },
                {
                    "symbol": "TQQQ",
                    "shares": 9.021652,
                    "market_value": 720.0,
                    "cost_basis": 675.0,
                    "current_price": 79.81,
                    "unrealized_pnl": 45.0,
                },
            ],
        },
    )

    result = cycle._write_current_portfolio_csv(source, destination)

    assert result == destination
    with destination.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["symbol"] for row in rows] == ["SOXL", "TQQQ"]
    assert float(rows[0]["market_value"]) == 1200.0
    assert float(rows[1]["cost_basis"]) == 675.0
    assert not list(tmp_path.glob(".*current_portfolio_positions.csv.*.tmp"))


def test_current_portfolio_adapter_rejects_non_paper_evidence(tmp_path: Path) -> None:
    source = tmp_path / "paper_portfolio_positions.json"
    _write_json(source, {"paper_trade_mode": False, "positions": []})

    with pytest.raises(ValueError, match="paper_trade_mode must be true"):
        cycle._write_current_portfolio_csv(source, tmp_path / "current.csv")


def test_current_portfolio_adapter_does_not_mutate_persistent_open_positions(tmp_path: Path) -> None:
    ledger = tmp_path / "paper_ledger"
    open_positions = ledger / "open_positions.json"
    source = ledger / "paper_portfolio_positions.json"
    original = {
        "paper_trade_mode": True,
        "positions": [
            {
                "symbol": "SOXL",
                "shares": 8.04145854,
                "entry_price": 139.89999389648438,
                "cost_basis": 1125.0,
            },
            {
                "symbol": "TQQQ",
                "shares": 9.021652,
                "entry_price": 74.81999969482422,
                "cost_basis": 675.0,
            },
        ],
    }
    _write_json(open_positions, original)
    _write_json(
        source,
        {
            "paper_trade_mode": True,
            "position_count": 2,
            "positions": [
                {"symbol": "SOXL", "shares": 8.04145854, "market_value": 1200.0, "cost_basis": 1125.0},
                {"symbol": "TQQQ", "shares": 9.021652, "market_value": 720.0, "cost_basis": 675.0},
            ],
        },
    )

    cycle._write_current_portfolio_csv(source, ledger / "current_portfolio_positions.csv")

    assert json.loads(open_positions.read_text(encoding="utf-8")) == original


def test_daily_cycle_has_no_paper_execution_dependency() -> None:
    source = Path("src/swing_trade_bot/swing_daily_cycle.py").read_text(encoding="utf-8").lower()
    assert "paper_execution_engine" not in source
    assert "run_paper_execution" not in source
    assert "robinhood" not in source


def test_runtime_refresh_uses_external_allocation_discovery_not_literal_capital() -> None:
    source = Path("src/swing_trade_bot/swing_daily_cycle.py").read_text(encoding="utf-8")
    assert "load_discovered_strategy_allocations" in source
    assert "resolve_strategy_allocation_evidence" in source
    assert "4500.0" not in source
    assert "4500" not in source

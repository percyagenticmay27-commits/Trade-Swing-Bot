from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from swing_trade_bot.paper_execution_engine import execute_allocations


def _write_allocations(path: Path) -> None:
    path.write_text(json.dumps({
        "paper_trade_mode": True,
        "allocations": [
            {"symbol": "AAA", "allocation_percent": 25.0, "active_strategy": "Strategy A"},
            {"symbol": "BBB", "allocation_percent": 15.0, "active_strategy": "Strategy B"},
            {"symbol": "SGOV", "allocation_percent": 60.0, "active_strategy": ""},
        ],
    }), encoding="utf-8")


def _write_market(path: Path, close: float) -> None:
    path.write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        f"2026-07-31,{close},{close},{close},{close},{close},1000\n",
        encoding="utf-8",
    )


def test_creates_positions_and_buy_history(tmp_path: Path) -> None:
    allocations = tmp_path / "allocations.json"
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    data_dir.mkdir()
    _write_allocations(allocations)
    _write_market(data_dir / "AAA.csv", 100.0)
    _write_market(data_dir / "BBB.csv", 50.0)

    report = execute_allocations(
        allocations_path=allocations,
        data_dir=data_dir,
        state_dir=state_dir,
        account_capital=10_000.0,
        as_of=date(2026, 7, 31),
    )

    assert [position.symbol for position in report.positions] == ["AAA", "BBB"]
    assert report.invested_capital == 4000.0
    assert report.cash_balance == 6000.0
    assert len(report.trades) == 2
    assert (state_dir / "open_positions.json").exists()
    assert (state_dir / "trade_history.json").exists()
    assert (state_dir / "paper_portfolio_summary.json").exists()


def test_rerun_does_not_duplicate_buys(tmp_path: Path) -> None:
    allocations = tmp_path / "allocations.json"
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    data_dir.mkdir()
    _write_allocations(allocations)
    _write_market(data_dir / "AAA.csv", 100.0)
    _write_market(data_dir / "BBB.csv", 50.0)

    execute_allocations(
        allocations_path=allocations,
        data_dir=data_dir,
        state_dir=state_dir,
        account_capital=10_000.0,
        as_of=date(2026, 7, 31),
    )
    report = execute_allocations(
        allocations_path=allocations,
        data_dir=data_dir,
        state_dir=state_dir,
        account_capital=10_000.0,
        as_of=date(2026, 7, 31),
    )

    assert report.trades == ()
    history = json.loads((state_dir / "trade_history.json").read_text(encoding="utf-8"))
    assert len(history["trades"]) == 2


def test_marks_existing_position_to_market(tmp_path: Path) -> None:
    allocations = tmp_path / "allocations.json"
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    data_dir.mkdir()
    _write_allocations(allocations)
    _write_market(data_dir / "AAA.csv", 100.0)
    _write_market(data_dir / "BBB.csv", 50.0)
    execute_allocations(
        allocations_path=allocations,
        data_dir=data_dir,
        state_dir=state_dir,
        account_capital=10_000.0,
        as_of=date(2026, 7, 31),
    )
    _write_market(data_dir / "AAA.csv", 110.0)

    report = execute_allocations(
        allocations_path=allocations,
        data_dir=data_dir,
        state_dir=state_dir,
        account_capital=10_000.0,
        as_of=date(2026, 7, 31),
    )
    aaa = next(position for position in report.positions if position.symbol == "AAA")
    assert aaa.unrealized_pnl == 250.0
    assert aaa.unrealized_pnl_percent == 10.0
    assert report.portfolio_value == 10250.0


def test_missing_market_data_fails_without_overwriting_state(tmp_path: Path) -> None:
    allocations = tmp_path / "allocations.json"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    sentinel = state_dir / "open_positions.json"
    sentinel.write_text('{"sentinel": true}\n', encoding="utf-8")
    _write_allocations(allocations)

    with pytest.raises(FileNotFoundError):
        execute_allocations(
            allocations_path=allocations,
            data_dir=tmp_path / "missing",
            state_dir=state_dir,
            account_capital=10_000.0,
            as_of=date(2026, 7, 31),
        )

    assert json.loads(sentinel.read_text(encoding="utf-8")) == {"sentinel": True}


def test_rejects_nonpositive_account_capital(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        execute_allocations(
            allocations_path=tmp_path / "allocations.json",
            data_dir=tmp_path,
            state_dir=tmp_path / "state",
            account_capital=0.0,
        )


def test_source_has_no_broker_or_order_integration() -> None:
    source = Path("src/swing_trade_bot/paper_execution_engine.py").read_text(encoding="utf-8").lower()
    forbidden = ("import robinhood", "place_order(", "cancel_order(", "transfer_funds(")
    assert all(value not in source for value in forbidden)

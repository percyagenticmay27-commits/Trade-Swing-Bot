import json
from datetime import date
from pathlib import Path

import pytest

from swing_trade_bot.paper_portfolio_manager import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    DIRECT_DATABASE_WRITES,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    build_and_write_paper_portfolio_report,
    build_paper_portfolio_report,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_csv(path: Path, rows: list[tuple[str, float, float | None]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "Date,Open,High,Low,Close,Adj Close,Volume\n"
    for day, close, adjusted in rows:
        adj = close if adjusted is None else adjusted
        text += f"{day},{close},{close},{close},{close},{adj},1000\n"
    path.write_text(text, encoding="utf-8")


def _ledger(tmp_path: Path) -> Path:
    ledger = tmp_path / "ledger"
    _write_json(
        ledger / "open_positions.json",
        {
            "positions": [
                {
                    "symbol": "AAA",
                    "entry_date": "2026-08-01",
                    "entry_price": 100.0,
                    "shares": 10.0,
                    "cost_basis": 1000.0,
                    "allocation_percent": 25.0,
                    "active_strategy": "Strategy A",
                },
                {
                    "symbol": "BBB",
                    "entry_date": "2026-08-01",
                    "entry_price": 50.0,
                    "shares": 10.0,
                    "cost_basis": 500.0,
                    "allocation_percent": 15.0,
                    "active_strategy": "Strategy A",
                },
            ]
        },
    )
    return ledger


def test_marks_positions_to_market_and_preserves_cash(tmp_path):
    ledger = _ledger(tmp_path)
    data = tmp_path / "data"
    _write_csv(data / "AAA.csv", [("2026-08-01", 100.0, 100.0), ("2026-08-02", 110.0, 110.0)])
    _write_csv(data / "BBB.csv", [("2026-08-01", 50.0, 50.0), ("2026-08-02", 45.0, 45.0)])

    report = build_paper_portfolio_report(
        ledger_dir=ledger,
        data_dir=data,
        account_capital=4500.0,
        as_of=date(2026, 8, 2),
    )

    assert report.invested_capital == 1500.0
    assert report.cash_balance == 3000.0
    assert report.positions_market_value == 1550.0
    assert report.portfolio_value == 4550.0
    assert report.unrealized_pnl == 50.0
    assert report.portfolio_return_percent == pytest.approx(1.111111)
    assert report.position_count == 2
    assert report.valuation_source == "PAPER_LEDGER_SPLIT_ADJUSTED_MARK_TO_MARKET"


def test_split_adjustment_updates_shares_and_entry_price_without_changing_cost_basis(tmp_path):
    ledger = tmp_path / "ledger"
    _write_json(
        ledger / "open_positions.json",
        {
            "positions": [
                {
                    "symbol": "SOXL",
                    "entry_date": "2026-06-22",
                    "entry_price": 300.0,
                    "shares": 3.75,
                    "cost_basis": 1125.0,
                    "allocation_percent": 25.0,
                    "active_strategy": "Strategy A",
                }
            ]
        },
    )
    data = tmp_path / "data"
    _write_csv(
        data / "SOXL.csv",
        [
            ("2026-06-22", 300.0, 150.0),
            ("2026-08-04", 138.0, 138.0),
        ],
    )

    report = build_paper_portfolio_report(
        ledger_dir=ledger,
        data_dir=data,
        account_capital=4500.0,
        as_of=date(2026, 8, 4),
    )
    position = report.positions[0]
    assert position.shares == 7.5
    assert position.entry_price == 150.0
    assert position.cost_basis == 1125.0
    assert position.current_price == 138.0
    assert position.market_value == 1035.0
    assert position.unrealized_pnl == -90.0
    assert position.split_adjustment_factor == 2.0
    assert position.price_source == "ADJ_CLOSE"


def test_stale_market_data_is_rejected(tmp_path):
    ledger = _ledger(tmp_path)
    data = tmp_path / "data"
    _write_csv(data / "AAA.csv", [("2026-07-20", 100.0, 100.0)])
    _write_csv(data / "BBB.csv", [("2026-07-20", 50.0, 50.0)])

    with pytest.raises(ValueError, match="stale market data"):
        build_paper_portfolio_report(
            ledger_dir=ledger,
            data_dir=data,
            account_capital=4500.0,
            as_of=date(2026, 8, 4),
            max_price_age_days=5,
        )


def test_writes_authoritative_summary_and_positions(tmp_path):
    ledger = _ledger(tmp_path)
    data = tmp_path / "data"
    _write_csv(data / "AAA.csv", [("2026-08-02", 100.0, 100.0)])
    _write_csv(data / "BBB.csv", [("2026-08-02", 50.0, 50.0)])

    report = build_and_write_paper_portfolio_report(
        ledger_dir=ledger,
        data_dir=data,
        output_dir=ledger,
        account_capital=4500.0,
        as_of=date(2026, 8, 2),
    )

    summary = json.loads((ledger / "paper_portfolio_summary.json").read_text(encoding="utf-8"))
    positions = json.loads((ledger / "paper_portfolio_positions.json").read_text(encoding="utf-8"))
    assert summary["portfolio_value"] == report.portfolio_value
    assert summary["position_count"] == 2
    assert summary["valuation_source"] == "PAPER_LEDGER_SPLIT_ADJUSTED_MARK_TO_MARKET"
    assert "positions" not in summary
    assert positions["position_count"] == 2
    assert len(positions["positions"]) == 2


def test_future_bar_is_excluded(tmp_path):
    ledger = _ledger(tmp_path)
    data = tmp_path / "data"
    _write_csv(data / "AAA.csv", [("2026-08-02", 100.0, 100.0), ("2026-08-04", 999.0, 999.0)])
    _write_csv(data / "BBB.csv", [("2026-08-02", 50.0, 50.0)])

    report = build_paper_portfolio_report(
        ledger_dir=ledger,
        data_dir=data,
        account_capital=4500.0,
        as_of=date(2026, 8, 3),
    )
    aaa = next(position for position in report.positions if position.symbol == "AAA")
    assert aaa.current_price == 100.0
    assert aaa.price_date == "2026-08-02"


def test_missing_market_data_fails_without_overwriting_existing_output(tmp_path):
    ledger = _ledger(tmp_path)
    output = ledger / "paper_portfolio_summary.json"
    output.write_text('{"preserved": true}', encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        build_and_write_paper_portfolio_report(
            ledger_dir=ledger,
            data_dir=tmp_path / "missing-data",
            output_dir=ledger,
            account_capital=4500.0,
        )

    assert json.loads(output.read_text(encoding="utf-8")) == {"preserved": True}


def test_cost_basis_cannot_exceed_account_capital(tmp_path):
    ledger = _ledger(tmp_path)
    data = tmp_path / "data"
    _write_csv(data / "AAA.csv", [("2026-08-02", 100.0, 100.0)])
    _write_csv(data / "BBB.csv", [("2026-08-02", 50.0, 50.0)])

    with pytest.raises(ValueError, match="exceeds account_capital"):
        build_paper_portfolio_report(
            ledger_dir=ledger,
            data_dir=data,
            account_capital=1000.0,
            as_of=date(2026, 8, 2),
        )


def test_safety_flags_are_locked_and_no_broker_imports_exist():
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert DIRECT_DATABASE_WRITES is False
    source = Path("src/swing_trade_bot/paper_portfolio_manager.py").read_text(encoding="utf-8").lower()
    assert "robin_stocks" not in source
    assert "place_order" not in source
    assert "trade_dividend_bot" not in source

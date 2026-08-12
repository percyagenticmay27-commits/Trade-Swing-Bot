import csv
import json
from pathlib import Path

from swing_trade_bot.swing_executive_summary import (
    build_swing_executive_rows,
    write_swing_executive_summary,
)


def test_builds_account_and_position_rows() -> None:
    kpi = {
        "strategy_id": "SWING-001",
        "allocated_capital": 4500.0,
        "portfolio_value": 4500.0,
        "cash_balance": 2700.0,
        "invested_capital": 1800.0,
        "position_count": 1,
        "trade_count": 1,
        "closed_trade_count": 0,
        "opportunity_quality": 23.88,
        "evidence_status": "AVAILABLE",
        "open_positions": [
            {
                "symbol": "SOXL",
                "shares": 3.0,
                "entry_price": 100.0,
                "current_price": 110.0,
                "active_strategy": "Strategy A",
                "confidence_level": "HIGH",
            }
        ],
    }
    rows = build_swing_executive_rows(kpi, report_date="2026-08-04")
    assert rows[0]["record_type"] == "ACCOUNT_SUMMARY"
    assert rows[1]["record_type"] == "POSITION"
    assert rows[1]["symbol"] == "SOXL"
    assert rows[1]["action"] == "BUY"
    assert rows[1]["market_value"] == 330.0
    assert rows[1]["unrealized_pnl"] == 30.0
    assert rows[1]["confidence"] == "HIGH"


def test_falls_back_to_portfolio_summary_positions() -> None:
    kpi = {"strategy_id": "SWING-001", "allocated_capital": 4500.0}
    summary = {"positions": [{"symbol": "TQQQ", "shares": 2, "entry_price": 80, "current_price": 82}]}
    rows = build_swing_executive_rows(kpi, summary, "2026-08-04")
    assert len(rows) == 2
    assert rows[1]["symbol"] == "TQQQ"


def test_writes_csv_atomically(tmp_path: Path) -> None:
    kpi_path = tmp_path / "kpi.json"
    portfolio_path = tmp_path / "portfolio.json"
    output = tmp_path / "executive.csv"
    kpi_path.write_text(
        json.dumps(
            {
                "strategy_id": "SWING-001",
                "allocated_capital": 4500.0,
                "portfolio_value": 4500.0,
                "open_positions": [{"symbol": "SOXL", "shares": 1, "entry_price": 20, "current_price": 21}],
            }
        ),
        encoding="utf-8",
    )
    portfolio_path.write_text("{}", encoding="utf-8")
    result = write_swing_executive_summary(output, kpi_path, portfolio_path)
    assert result == output
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["record_type"] for row in rows] == ["ACCOUNT_SUMMARY", "POSITION"]
    assert rows[1]["symbol"] == "SOXL"


def test_safety_flags_locked() -> None:
    from swing_trade_bot import swing_executive_summary as module

    assert module.PAPER_TRADE_MODE is True
    assert module.LIVE_TRADING_ENABLED is False
    assert module.BROKER_EXECUTION_ENABLED is False
    assert module.ORDER_PLACEMENT_ENABLED is False
    assert module.CAPITAL_MOVEMENT_ENABLED is False
    assert module.DIRECT_DATABASE_WRITES is False

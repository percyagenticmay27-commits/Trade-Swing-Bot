from __future__ import annotations

import csv
import json
from pathlib import Path

from swing_trade_bot.portfolio_manager import build_portfolio_manager_report


def test_build_report_auto_uses_current_paper_summary_account_value(tmp_path: Path) -> None:
    ledger = tmp_path / "paper_ledger"
    ledger.mkdir()
    current = ledger / "current_portfolio_positions.csv"
    current.write_text(
        "symbol,shares,market_value,cost_basis\n"
        "SOXL,8.0,1125,1125\n"
        "TQQQ,9.0,675,675\n",
        encoding="utf-8",
    )
    (ledger / "paper_portfolio_summary.json").write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "portfolio_value": 4500.0,
                "cash_balance": 2700.0,
            }
        ),
        encoding="utf-8",
    )
    targets = tmp_path / "portfolio_allocations.csv"
    targets.write_text(
        "symbol,confidence_level,active_strategy,rank,allocation_percent,theme,theme_allocation,cash_equivalent\n"
        "SOXL,HIGH,Strategy A,,25,Semiconductors,40,\n"
        "TQQQ,HIGH,Strategy A,,15,Technology,40,\n"
        "SGOV,RESERVE,,,60,Cash Equivalent,60,SGOV\n",
        encoding="utf-8",
    )

    result = build_portfolio_manager_report(
        current_portfolio_path=current,
        target_portfolio_path=targets,
        output_dir=tmp_path,
        paper_trade_mode=True,
    )

    actions = {row.symbol: row for row in result.actions}
    assert result.total_market_value == 4500.0
    assert actions["SOXL"].current_allocation == 25.0
    assert actions["TQQQ"].current_allocation == 15.0
    assert actions["SGOV"].current_allocation == 60.0
    assert actions["SOXL"].action == "HOLD"
    assert actions["TQQQ"].action == "HOLD"
    assert actions["SGOV"].action == "HOLD"

    with (tmp_path / "portfolio_manager_report.csv").open(newline="", encoding="utf-8") as handle:
        report = {row["symbol"]: row for row in csv.DictReader(handle)}
    assert float(report["SOXL"]["allocation_before"]) == 25.0
    assert float(report["SGOV"]["allocation_before"]) == 60.0


def test_cash_reserve_is_not_manufactured_as_current_holding(tmp_path: Path) -> None:
    ledger = tmp_path / "paper_ledger"
    ledger.mkdir()
    current = ledger / "current_portfolio_positions.csv"
    current.write_text(
        "symbol,shares,market_value,cost_basis\nSOXL,8.0,1125,1125\n",
        encoding="utf-8",
    )
    (ledger / "paper_portfolio_summary.json").write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "portfolio_value": 4500.0,
                "cash_balance": 3375.0,
            }
        ),
        encoding="utf-8",
    )
    targets = tmp_path / "target.csv"
    targets.write_text(
        "symbol,allocation_percent,cash_equivalent\nSOXL,25,\nSGOV,75,SGOV\n",
        encoding="utf-8",
    )

    build_portfolio_manager_report(
        current_portfolio_path=current,
        target_portfolio_path=targets,
        output_dir=tmp_path,
    )

    # The adapter remains a record of real holdings only; SGOV is represented
    # solely as reserve allocation math in manager output.
    assert "SGOV" not in current.read_text(encoding="utf-8")

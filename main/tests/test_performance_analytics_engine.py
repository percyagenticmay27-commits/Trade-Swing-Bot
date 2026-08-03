from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot.performance_analytics_engine import (
    build_and_write_performance_analytics_report,
    build_performance_analytics_report,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _safe(**values):
    return {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "direct_database_writes": False,
        **values,
    }


def _paths(tmp_path: Path):
    ledger = tmp_path / "paper_ledger"
    portfolio = ledger / "paper_portfolio_summary.json"
    closed = ledger / "closed_positions.json"
    history = ledger / "trade_history_summary.json"
    return ledger, portfolio, closed, history


def test_no_closed_trades_reports_partial_without_fabricated_win_rate(tmp_path: Path):
    _, portfolio, closed, history = _paths(tmp_path)
    _write(portfolio, _safe(account_capital=4500, portfolio_value=4500, cash_balance=2700,
                            invested_capital=1800, positions_market_value=1800,
                            unrealized_pnl=0, position_count=2))
    _write(closed, _safe(closed_trades=[]))
    _write(history, _safe(total_trade_events=2, realized_pnl=0))
    report = build_performance_analytics_report(
        portfolio_summary_path=portfolio,
        closed_positions_path=closed,
        trade_history_summary_path=history,
    )
    assert report.evidence_status == "PARTIAL"
    assert report.win_rate_percent is None
    assert report.profit_factor is None
    assert report.max_drawdown_percent is None
    assert report.closed_trade_count == 0


def test_closed_trades_calculate_core_metrics_and_strategy_breakdown(tmp_path: Path):
    _, portfolio, closed, history = _paths(tmp_path)
    _write(portfolio, _safe(account_capital=4500, portfolio_value=4575, cash_balance=2700,
                            invested_capital=1800, positions_market_value=1875,
                            unrealized_pnl=75, position_count=2))
    rows = [
        {"closed_trade_id": "C1", "symbol": "AAA", "realized_pnl": 100,
         "holding_days": 5, "active_strategy": "Strategy A"},
        {"closed_trade_id": "C2", "symbol": "BBB", "realized_pnl": -25,
         "holding_days": 3, "active_strategy": "Strategy A"},
        {"closed_trade_id": "C3", "symbol": "CCC", "realized_pnl": 0,
         "holding_days": 2, "active_strategy": "Strategy B"},
    ]
    _write(closed, _safe(closed_trades=rows))
    _write(history, _safe(total_trade_events=6, realized_pnl=75))
    report = build_performance_analytics_report(
        portfolio_summary_path=portfolio,
        closed_positions_path=closed,
        trade_history_summary_path=history,
    )
    assert report.evidence_status == "AVAILABLE"
    assert report.closed_trade_count == 3
    assert report.winning_trade_count == 1
    assert report.losing_trade_count == 1
    assert report.breakeven_trade_count == 1
    assert report.win_rate_percent == 50.0
    assert report.realized_pnl == 75.0
    assert report.total_pnl == 150.0
    assert report.portfolio_return_percent == pytest.approx(3.333333)
    assert report.profit_factor == 4.0
    assert report.average_gain == 100.0
    assert report.average_loss == -25.0
    assert [item.strategy_name for item in report.strategy_performance] == ["Strategy A", "Strategy B"]


def test_rejects_realized_pnl_mismatch(tmp_path: Path):
    _, portfolio, closed, history = _paths(tmp_path)
    _write(portfolio, _safe(account_capital=1000, portfolio_value=1000, cash_balance=1000,
                            invested_capital=0, positions_market_value=0,
                            unrealized_pnl=0, position_count=0))
    _write(closed, _safe(closed_trades=[{"closed_trade_id": "C1", "symbol": "AAA",
                                        "realized_pnl": 10, "holding_days": 1,
                                        "active_strategy": "Strategy A"}]))
    _write(history, _safe(total_trade_events=2, realized_pnl=9))
    with pytest.raises(ValueError, match="disagrees"):
        build_performance_analytics_report(
            portfolio_summary_path=portfolio,
            closed_positions_path=closed,
            trade_history_summary_path=history,
        )


def test_rejects_unsafe_source_evidence(tmp_path: Path):
    _, portfolio, closed, history = _paths(tmp_path)
    _write(portfolio, _safe(account_capital=1000, portfolio_value=1000, cash_balance=1000,
                            invested_capital=0, positions_market_value=0,
                            unrealized_pnl=0, position_count=0,
                            broker_execution_enabled=True))
    _write(closed, _safe(closed_trades=[]))
    _write(history, _safe(total_trade_events=0, realized_pnl=0))
    with pytest.raises(ValueError, match="unsafe value"):
        build_performance_analytics_report(
            portfolio_summary_path=portfolio,
            closed_positions_path=closed,
            trade_history_summary_path=history,
        )


def test_writes_json_csv_and_markdown_atomically(tmp_path: Path):
    ledger, portfolio, closed, history = _paths(tmp_path)
    _write(portfolio, _safe(account_capital=4500, portfolio_value=4500, cash_balance=2700,
                            invested_capital=1800, positions_market_value=1800,
                            unrealized_pnl=0, position_count=2))
    _write(closed, _safe(closed_trades=[]))
    _write(history, _safe(total_trade_events=2, realized_pnl=0))
    report = build_and_write_performance_analytics_report(
        ledger_dir=ledger,
        output_dir=ledger,
    )
    assert report.evidence_status == "PARTIAL"
    assert (ledger / "paper_performance.json").exists()
    assert (ledger / "paper_performance.csv").exists()
    assert (ledger / "paper_performance.md").exists()
    assert not list(ledger.glob("*.tmp"))


def test_safety_constants_are_locked():
    import swing_trade_bot.performance_analytics_engine as module

    assert module.PAPER_TRADE_MODE is True
    assert module.LIVE_TRADING_ENABLED is False
    assert module.BROKER_EXECUTION_ENABLED is False
    assert module.ORDER_PLACEMENT_ENABLED is False
    assert module.CAPITAL_MOVEMENT_ENABLED is False
    assert module.DIRECT_DATABASE_WRITES is False

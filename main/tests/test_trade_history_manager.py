from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot.trade_history_manager import (
    build_and_write_trade_history_report,
    build_trade_history_report,
)


def _write_history(path: Path, trades: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1.0", "trades": trades}), encoding="utf-8")


def _trade(
    trade_id: str,
    side: str,
    trade_date: str,
    price: float,
    shares: float,
    *,
    symbol: str = "SOXX",
    reason: str = "TEST",
) -> dict:
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "side": side,
        "trade_date": trade_date,
        "price": price,
        "shares": shares,
        "notional": round(price * shares, 2),
        "active_strategy": "Strategy A",
        "reason": reason,
        "paper_trade_mode": True,
    }


def _write_market(path: Path, rows: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "Date,Open,High,Low,Close,Adj Close,Volume\n"
    for day, price in rows:
        text += f"{day},{price},{price},{price},{price},{price},1000\n"
    path.write_text(text, encoding="utf-8")


def test_buy_only_history_creates_open_lot_and_unavailable_win_rate(tmp_path: Path) -> None:
    path = tmp_path / "trade_history.json"
    _write_history(path, [_trade("BUY-1", "BUY", "2026-07-01", 100.0, 5.0)])

    report = build_trade_history_report(trade_history_path=path)

    assert report.total_trade_events == 1
    assert report.buy_event_count == 1
    assert report.sell_event_count == 0
    assert report.open_lot_count == 1
    assert report.closed_trade_count == 0
    assert report.win_rate_percent is None
    assert report.warnings


def test_fifo_sell_calculates_realized_profit(tmp_path: Path) -> None:
    path = tmp_path / "trade_history.json"
    _write_history(
        path,
        [
            _trade("BUY-1", "BUY", "2026-07-01", 100.0, 5.0),
            _trade("BUY-2", "BUY", "2026-07-02", 110.0, 5.0),
            _trade("SELL-1", "SELL", "2026-07-10", 120.0, 7.0, reason="TARGET_EXIT"),
        ],
    )

    report = build_trade_history_report(trade_history_path=path)

    assert report.closed_trade_count == 2
    assert report.open_lot_count == 1
    assert report.realized_pnl == 120.0
    assert report.winning_trade_count == 2
    assert report.win_rate_percent == 100.0
    assert report.open_lots[0].remaining_shares == 3.0


def test_closed_trade_drawdown_stops_at_actual_exit_date(tmp_path: Path) -> None:
    history = tmp_path / "paper_ledger/trade_history.json"
    data = tmp_path / "data"
    _write_history(
        history,
        [
            _trade("BUY-1", "BUY", "2026-08-01", 100.0, 2.0),
            _trade("SELL-1", "SELL", "2026-08-04", 110.0, 2.0, reason="TARGET_EXIT"),
        ],
    )
    _write_market(
        data / "SOXX.csv",
        [
            ("2026-08-01", 100.0),
            ("2026-08-02", 120.0),
            ("2026-08-03", 90.0),
            ("2026-08-04", 110.0),
            ("2026-08-05", 10.0),
        ],
    )

    report = build_trade_history_report(trade_history_path=history, data_dir=data)

    closed = report.closed_trades[0]
    assert closed.exit_date == "2026-08-04"
    assert closed.max_drawdown_amount == 60.0
    assert closed.max_drawdown_percent == 25.0
    assert closed.max_drawdown_trough_date == "2026-08-03"
    assert closed.realized_pnl == 20.0
    assert report.realized_pnl == 20.0


def test_partial_fifo_exit_uses_each_entry_lot_and_matched_shares(tmp_path: Path) -> None:
    history = tmp_path / "paper_ledger/trade_history.json"
    data = tmp_path / "data"
    _write_history(
        history,
        [
            _trade("BUY-1", "BUY", "2026-08-01", 100.0, 5.0),
            _trade("BUY-2", "BUY", "2026-08-02", 110.0, 5.0),
            _trade("SELL-1", "SELL", "2026-08-04", 120.0, 7.0, reason="TARGET_EXIT"),
        ],
    )
    _write_market(
        data / "SOXX.csv",
        [
            ("2026-08-01", 100.0),
            ("2026-08-02", 110.0),
            ("2026-08-03", 90.0),
            ("2026-08-04", 120.0),
        ],
    )

    report = build_trade_history_report(trade_history_path=history, data_dir=data)

    first, second = report.closed_trades
    assert (first.buy_trade_id, first.shares, first.cost_basis, first.realized_pnl) == (
        "BUY-1",
        5.0,
        500.0,
        100.0,
    )
    assert first.max_drawdown_amount == 100.0
    assert (second.buy_trade_id, second.shares, second.cost_basis, second.realized_pnl) == (
        "BUY-2",
        2.0,
        220.0,
        20.0,
    )
    assert second.max_drawdown_amount == 40.0
    assert report.realized_pnl == 120.0
    assert report.open_lots[0].source_trade_id == "BUY-2"
    assert report.open_lots[0].remaining_shares == 3.0


def test_losing_trade_is_recorded(tmp_path: Path) -> None:
    path = tmp_path / "trade_history.json"
    _write_history(
        path,
        [
            _trade("BUY-1", "BUY", "2026-07-01", 100.0, 2.0),
            _trade("SELL-1", "SELL", "2026-07-03", 90.0, 2.0),
        ],
    )
    report = build_trade_history_report(trade_history_path=path)
    assert report.realized_pnl == -20.0
    assert report.losing_trade_count == 1
    assert report.win_rate_percent == 0.0


def test_sell_cannot_exceed_available_shares(tmp_path: Path) -> None:
    path = tmp_path / "trade_history.json"
    _write_history(
        path,
        [
            _trade("BUY-1", "BUY", "2026-07-01", 100.0, 1.0),
            _trade("SELL-1", "SELL", "2026-07-02", 110.0, 2.0),
        ],
    )
    with pytest.raises(ValueError, match="exceeds available"):
        build_trade_history_report(trade_history_path=path)


def test_duplicate_trade_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "trade_history.json"
    _write_history(
        path,
        [
            _trade("DUP", "BUY", "2026-07-01", 100.0, 1.0),
            _trade("DUP", "BUY", "2026-07-02", 101.0, 1.0),
        ],
    )
    with pytest.raises(ValueError, match="duplicate trade_id"):
        build_trade_history_report(trade_history_path=path)


def test_non_paper_trade_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "trade_history.json"
    row = _trade("BUY-1", "BUY", "2026-07-01", 100.0, 1.0)
    row["paper_trade_mode"] = False
    _write_history(path, [row])
    with pytest.raises(ValueError, match="paper_trade_mode=true"):
        build_trade_history_report(trade_history_path=path)


def test_notional_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "trade_history.json"
    row = _trade("BUY-1", "BUY", "2026-07-01", 100.0, 1.0)
    row["notional"] = 5.0
    _write_history(path, [row])
    with pytest.raises(ValueError, match="notional"):
        build_trade_history_report(trade_history_path=path)


def test_outputs_are_written_atomically_and_are_read_only_evidence(tmp_path: Path) -> None:
    history = tmp_path / "trade_history.json"
    output = tmp_path / "out"
    _write_history(history, [_trade("BUY-1", "BUY", "2026-07-01", 100.0, 1.0)])

    report = build_and_write_trade_history_report(
        trade_history_path=history,
        output_dir=output,
    )

    assert (output / "managed_trade_history.json").exists()
    assert (output / "closed_positions.json").exists()
    closed = json.loads((output / "closed_positions.json").read_text(encoding="utf-8"))
    assert closed["closed_trade_count"] == 0
    assert closed["closed_trades"] == []
    assert (output / "trade_history_summary.json").exists()
    summary = json.loads((output / "trade_history_summary.json").read_text(encoding="utf-8"))
    assert summary["paper_trade_mode"] is True
    assert summary["live_trading_enabled"] is False
    assert summary["broker_execution_enabled"] is False
    assert summary["order_placement_enabled"] is False
    assert summary["capital_movement_enabled"] is False
    assert summary["direct_database_writes"] is False
    assert report.errors == ()

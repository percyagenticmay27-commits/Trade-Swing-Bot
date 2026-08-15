from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.trade_history_manager import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    build_and_write_trade_history_report,
    build_trade_history_report,
)


def _write_history(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "trades": [
                    {
                        "trade_id": "BUY-1",
                        "symbol": "AAA",
                        "side": "BUY",
                        "trade_date": "2026-07-01",
                        "price": 100.0,
                        "shares": 5.0,
                        "notional": 500.0,
                        "active_strategy": "Strategy A",
                        "reason": "ENTRY",
                        "paper_trade_mode": True,
                    },
                    {
                        "trade_id": "SELL-1",
                        "symbol": "AAA",
                        "side": "SELL",
                        "trade_date": "2026-07-04",
                        "price": 115.0,
                        "shares": 5.0,
                        "notional": 575.0,
                        "active_strategy": "Strategy A",
                        "reason": "TARGET_EXIT",
                        "paper_trade_mode": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_market_data(path: Path, rows: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Date,Open,High,Low,Close,Adj Close,Volume"]
    for day, price in rows:
        lines.append(f"{day},{price},{price},{price},{price},{price},1000")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_closed_trade_preserves_authoritative_lifetime_drawdown(tmp_path: Path) -> None:
    history = tmp_path / "ledger/trade_history.json"
    data = tmp_path / "data"
    _write_history(history)
    _write_market_data(
        data / "AAA.csv",
        [
            ("2026-07-01", 100.0),
            ("2026-07-02", 120.0),
            ("2026-07-03", 90.0),
            ("2026-07-04", 115.0),
        ],
    )

    report = build_trade_history_report(
        trade_history_path=history,
        data_dir=data,
    )

    assert report.closed_trade_count == 1
    row = report.closed_trades[0]
    assert row.realized_pnl == 75.0
    assert row.max_drawdown_amount == 150.0
    assert row.max_drawdown_percent == 25.0
    assert row.max_drawdown_peak_price == 120.0
    assert row.max_drawdown_peak_date == "2026-07-02"
    assert row.max_drawdown_trough_price == 90.0
    assert row.max_drawdown_trough_date == "2026-07-03"
    assert row.drawdown_source == "COMPLETED_DAILY_MARK_TO_MARKET_BARS_SINCE_ENTRY"


def test_closed_position_output_persists_drawdown_fields(tmp_path: Path) -> None:
    history = tmp_path / "ledger/trade_history.json"
    output = tmp_path / "out"
    data = tmp_path / "data"
    _write_history(history)
    _write_market_data(
        data / "AAA.csv",
        [
            ("2026-07-01", 100.0),
            ("2026-07-02", 120.0),
            ("2026-07-03", 90.0),
            ("2026-07-04", 115.0),
        ],
    )

    build_and_write_trade_history_report(
        trade_history_path=history,
        output_dir=output,
        data_dir=data,
    )
    payload = json.loads((output / "closed_positions.json").read_text(encoding="utf-8"))
    row = payload["closed_trades"][0]
    assert row["max_drawdown_amount"] == 150.0
    assert row["max_drawdown_percent"] == 25.0
    assert row["max_drawdown_peak_date"] == "2026-07-02"
    assert row["max_drawdown_trough_date"] == "2026-07-03"


def test_truncated_closed_trade_history_remains_truthfully_unavailable(tmp_path: Path) -> None:
    history = tmp_path / "ledger/trade_history.json"
    data = tmp_path / "data"
    _write_history(history)
    _write_market_data(
        data / "AAA.csv",
        [
            ("2026-07-02", 120.0),
            ("2026-07-03", 90.0),
            ("2026-07-04", 115.0),
        ],
    )

    report = build_trade_history_report(
        trade_history_path=history,
        data_dir=data,
    )
    row = report.closed_trades[0]
    assert row.max_drawdown_amount is None
    assert row.max_drawdown_percent is None
    assert any("full holding period" in warning for warning in report.warnings)


def test_existing_callers_without_market_history_remain_backward_compatible(tmp_path: Path) -> None:
    history = tmp_path / "trade_history.json"
    _write_history(history)
    report = build_trade_history_report(trade_history_path=history)
    assert report.closed_trades[0].max_drawdown_amount is None
    assert report.closed_trades[0].max_drawdown_percent is None


def test_closed_drawdown_path_preserves_paper_safety() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False

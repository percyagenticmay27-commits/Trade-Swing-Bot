from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot.closed_trade_excursion_archive import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    DIRECT_DATABASE_WRITES,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    enrich_and_archive_closed_trade_excursions,
)


def _write_closed(path: Path, *, entry_price: float = 100.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "paper_trade_mode": True,
                "closed_trade_count": 1,
                "closed_trades": [
                    {
                        "closed_trade_id": "CLOSED-BUY-1-SELL-1-1",
                        "symbol": "AAA",
                        "buy_trade_id": "BUY-1",
                        "sell_trade_id": "SELL-1",
                        "entry_date": "2026-08-01",
                        "exit_date": "2026-08-04",
                        "entry_price": entry_price,
                        "exit_price": 110.0,
                        "shares": 2.0,
                        "cost_basis": 200.0,
                        "proceeds": 220.0,
                        "realized_pnl": 20.0,
                        "realized_pnl_percent": 10.0,
                        "holding_days": 3,
                        "active_strategy": "Strategy A",
                        "exit_reason": "TEST_EXIT",
                        "status": "CLOSED",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_market(path: Path, rows: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "Date,Open,High,Low,Close,Adj Close,Volume\n"
    for day, price in rows:
        text += f"{day},{price},{price},{price},{price},{price},1000\n"
    path.write_text(text, encoding="utf-8")


def test_closed_trade_drawdown_is_calculated_and_archived(tmp_path: Path) -> None:
    closed = tmp_path / "ledger/closed_positions.json"
    data = tmp_path / "data"
    _write_closed(closed)
    _write_market(
        data / "AAA.csv",
        [
            ("2026-08-01", 100.0),
            ("2026-08-02", 120.0),
            ("2026-08-03", 90.0),
            ("2026-08-04", 110.0),
        ],
    )

    payload = enrich_and_archive_closed_trade_excursions(
        closed_positions_path=closed,
        data_dir=data,
    )
    row = payload["closed_trades"][0]

    assert row["max_drawdown_amount"] == 60.0
    assert row["max_drawdown_percent"] == 25.0
    assert row["max_drawdown_peak_date"] == "2026-08-02"
    assert row["max_drawdown_trough_date"] == "2026-08-03"
    assert row["drawdown_source"] == "COMPLETED_DAILY_MARK_TO_MARKET_BARS_SINCE_ENTRY"
    archive = json.loads((closed.parent / "closed_trade_excursion_archive.json").read_text())
    assert archive["closed_trades"]["CLOSED-BUY-1-SELL-1-1"]["max_drawdown_percent"] == 25.0


def test_archived_drawdown_survives_later_truncated_market_history(tmp_path: Path) -> None:
    closed = tmp_path / "ledger/closed_positions.json"
    data = tmp_path / "data"
    _write_closed(closed)
    _write_market(
        data / "AAA.csv",
        [
            ("2026-08-01", 100.0),
            ("2026-08-02", 120.0),
            ("2026-08-03", 90.0),
            ("2026-08-04", 110.0),
        ],
    )
    enrich_and_archive_closed_trade_excursions(closed_positions_path=closed, data_dir=data)

    # Simulate the deterministic trade-history rebuild removing enriched fields,
    # followed by a shortened market-data window that no longer covers entry.
    _write_closed(closed)
    _write_market(data / "AAA.csv", [("2026-08-04", 110.0)])
    payload = enrich_and_archive_closed_trade_excursions(closed_positions_path=closed, data_dir=data)

    row = payload["closed_trades"][0]
    assert row["max_drawdown_amount"] == 60.0
    assert row["max_drawdown_percent"] == 25.0
    assert payload["drawdown_warnings"] == []


def test_archive_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    closed = tmp_path / "ledger/closed_positions.json"
    data = tmp_path / "data"
    _write_closed(closed)
    _write_market(data / "AAA.csv", [("2026-08-01", 100.0), ("2026-08-04", 110.0)])
    enrich_and_archive_closed_trade_excursions(closed_positions_path=closed, data_dir=data)

    _write_closed(closed, entry_price=101.0)
    with pytest.raises(ValueError, match="identity mismatch"):
        enrich_and_archive_closed_trade_excursions(closed_positions_path=closed, data_dir=data)


def test_missing_history_does_not_fabricate_closed_drawdown(tmp_path: Path) -> None:
    closed = tmp_path / "ledger/closed_positions.json"
    data = tmp_path / "data"
    _write_closed(closed)
    _write_market(data / "AAA.csv", [("2026-08-04", 110.0)])

    payload = enrich_and_archive_closed_trade_excursions(closed_positions_path=closed, data_dir=data)
    row = payload["closed_trades"][0]
    assert "max_drawdown_amount" not in row
    assert "max_drawdown_percent" not in row
    assert payload["drawdown_warnings"]


def test_closed_trade_excursion_archive_safety_is_locked() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert DIRECT_DATABASE_WRITES is False

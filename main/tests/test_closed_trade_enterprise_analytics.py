from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.enterprise_strategy_kpi_publisher_v21 import (
    build_enterprise_strategy_kpis_v21,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_canonical_closed_trades_are_published_as_trade_analytics(tmp_path: Path) -> None:
    _write(tmp_path / "portfolio_allocations.json", {"allocations": []})
    _write(
        tmp_path / "paper_ledger/closed_positions.json",
        {
            "schema_version": "1.0",
            "paper_trade_mode": True,
            "closed_trade_count": 1,
            "closed_trades": [
                {
                    "closed_trade_id": "CLOSED-BUY-1-SELL-1-1",
                    "symbol": "SOXL",
                    "entry_date": "2026-08-04",
                    "exit_date": "2026-08-14",
                    "entry_price": 100.0,
                    "exit_price": 110.0,
                    "shares": 2.0,
                    "cost_basis": 200.0,
                    "realized_pnl": 20.0,
                    "realized_pnl_percent": 10.0,
                    "holding_days": 10,
                    "active_strategy": "Strategy A",
                    "exit_reason": "TARGET_EXIT",
                    "status": "CLOSED",
                    "max_drawdown_amount": 60.0,
                    "max_drawdown_percent": 25.0,
                }
            ],
        },
    )

    payload = build_enterprise_strategy_kpis_v21(
        tmp_path,
        strategy_allocations={"strategy_allocations": {"SWING-001": 4500.0}},
    )

    analytics = payload["trade_analytics"]
    assert analytics["closed_position_count"] == 1
    row = analytics["closed_positions"][0]
    assert row["symbol"] == "SOXL"
    assert row["entry_date"] == "2026-08-04"
    assert row["exit_date"] == "2026-08-14"
    assert row["exit_price"] == 110.0
    assert row["realized_pnl"] == 20.0
    assert row["realized_pnl_percent"] == 10.0
    assert row["holding_days"] == 10.0
    assert row["exit_reason"] == "TARGET_EXIT"
    assert row["max_drawdown_amount"] == 60.0
    assert row["max_drawdown_percent"] == 25.0
    assert payload["dashboard_sections"]["trade_analytics"]["closed_position_count"] == 1

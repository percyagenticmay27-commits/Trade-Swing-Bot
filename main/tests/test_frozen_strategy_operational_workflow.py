from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from swing_trade_bot.frozen_strategy_operational_workflow import (
    AUTO_PROMOTION_ENABLED,
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_POSITION_CREATION_ENABLED,
    PAPER_TRADE_MODE,
    SHADOW_ALLOCATION_MODEL,
    build_and_write_frozen_strategy_evidence,
)

NY = ZoneInfo("America/New_York")


def _config(path: Path) -> None:
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "strategies": [
            {
                "strategy_id": "TEST_PRIMARY",
                "name": "Primary",
                "signal_symbol": "SOXL",
                "vehicle_symbol": "SOXL",
                "timeframe": "1H",
                "engine_id": "ZERO_LAG",
                "parameters": {"length": 10, "multiplier": 0.1},
                "catastrophic_stop_percent": 20,
                "assignment_mode": "DIRECT",
                "enabled": True,
                "paper_trade_mode": True,
            },
            {
                "strategy_id": "TEST_SHADOW",
                "name": "Shadow",
                "signal_symbol": "SOXL",
                "vehicle_symbol": "SOXL",
                "timeframe": "1H",
                "engine_id": "ZERO_LAG",
                "parameters": {"length": 10, "multiplier": 0.1},
                "catastrophic_stop_percent": 20,
                "assignment_mode": "SHADOW",
                "enabled": True,
                "paper_trade_mode": True,
            },
        ],
        "symbols": [{
            "symbol": "SOXL",
            "primary_strategy_id": "TEST_PRIMARY",
            "shadow_strategy_ids": ["TEST_SHADOW"],
            "shadow_slot_3": None,
            "research_status": "TEST",
        }],
    }), encoding="utf-8")


def _positions(path: Path, shares: float = 8.25) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "shares", "market_value", "cost_basis"])
        writer.writeheader()
        writer.writerow({"symbol": "SOXL", "shares": shares, "market_value": 800, "cost_basis": 800})


def _intraday(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 5, 9, 30, tzinfo=NY)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        price = 100.0
        for minute in range(60 * 6 * 15):
            day = minute // 390
            slot = minute % 390
            timestamp = (start + timedelta(days=day)).replace(hour=9, minute=30) + timedelta(minutes=slot)
            close = price if minute < 390 * 12 else price + 15.0
            writer.writerow({
                "timestamp": timestamp.isoformat(),
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1000,
            })


def test_operational_workflow_uses_same_primary_quantity_for_direct_and_shadow(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    positions = tmp_path / "positions.csv"
    data = tmp_path / "intraday"
    performance = tmp_path / "performance.json"
    ledger = tmp_path / "ledger.json"
    _config(config)
    _positions(positions, 8.25)
    _intraday(data / "SOXL.csv")

    payload = build_and_write_frozen_strategy_evidence(
        config_path=config,
        intraday_data_dir=data,
        primary_positions_path=positions,
        performance_path=performance,
        ledger_path=ledger,
    )

    assert len(payload["rows"]) == 2
    assert {row["assignment_mode"] for row in payload["rows"]} == {"DIRECT", "SHADOW"}
    available = [row for row in payload["rows"] if row["evidence_status"] == "AVAILABLE"]
    assert len(available) == 2
    assert all(row["primary_reference_quantity"] == 8.25 for row in available)
    assert all(row["shadow_test_quantity"] == 8.25 for row in available)
    assert payload["shadow_allocation_model"] == SHADOW_ALLOCATION_MODEL
    assert performance.is_file()
    assert ledger.is_file()
    saved = json.loads(performance.read_text(encoding="utf-8"))
    assert "ledger_rows" not in saved


def test_missing_intraday_data_fails_closed_without_crashing(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    positions = tmp_path / "positions.csv"
    _config(config)
    _positions(positions)
    payload = build_and_write_frozen_strategy_evidence(
        config_path=config,
        intraday_data_dir=tmp_path / "missing",
        primary_positions_path=positions,
        performance_path=tmp_path / "performance.json",
        ledger_path=tmp_path / "ledger.json",
    )
    assert all(row["evidence_status"] == "MISSING_INTRADAY_MARKET_DATA" for row in payload["rows"])


def test_operational_workflow_has_no_execution_or_promotion_authority() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert PAPER_POSITION_CREATION_ENABLED is False
    assert AUTO_PROMOTION_ENABLED is False

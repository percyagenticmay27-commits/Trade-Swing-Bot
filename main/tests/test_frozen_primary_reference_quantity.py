import csv
import json
from pathlib import Path

from swing_trade_bot.frozen_primary_reference_quantity import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_POSITION_CREATION_ENABLED,
    PAPER_TRADE_MODE,
    refresh_frozen_primary_reference_quantities,
)


def _config(path: Path) -> None:
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "strategies": [{
            "strategy_id": "SOXL_PRIMARY",
            "name": "Primary",
            "signal_symbol": "SOXL",
            "vehicle_symbol": "SOXL",
            "timeframe": "1H",
            "engine_id": "BIGBELUGA_RANGE",
            "parameters": {},
            "catastrophic_stop_percent": 20.0,
            "assignment_mode": "DIRECT",
            "enabled": True,
            "paper_trade_mode": True,
        }],
        "symbols": [{
            "symbol": "SOXL",
            "primary_strategy_id": "SOXL_PRIMARY",
            "shadow_strategy_ids": [],
            "shadow_slot_3": None,
            "research_status": "TEST",
        }],
    }), encoding="utf-8")


def _positions(path: Path, shares: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "shares", "market_value", "cost_basis"])
        writer.writeheader()
        writer.writerow({"symbol": "SOXL", "shares": shares, "market_value": 900, "cost_basis": 1000})


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_open_primary_quantity_is_snapshotted(tmp_path):
    config = tmp_path / "config.json"
    current = tmp_path / "current.csv"
    reference = tmp_path / "reference.csv"
    _config(config)
    _positions(current, 8.25)

    report = refresh_frozen_primary_reference_quantities(
        config_path=config, current_positions_path=current, reference_path=reference
    )

    assert report["rows"][0]["status"] == "UPDATED_FROM_OPEN_PRIMARY"
    assert report["rows"][0]["shares"] == 8.25
    assert float(_read(reference)[0]["shares"]) == 8.25


def test_reference_quantity_is_preserved_while_primary_is_flat(tmp_path):
    config = tmp_path / "config.json"
    current = tmp_path / "current.csv"
    reference = tmp_path / "reference.csv"
    _config(config)
    _positions(current, 8.25)
    refresh_frozen_primary_reference_quantities(
        config_path=config, current_positions_path=current, reference_path=reference
    )

    current.write_text("symbol,shares,market_value,cost_basis\n", encoding="utf-8")
    report = refresh_frozen_primary_reference_quantities(
        config_path=config, current_positions_path=current, reference_path=reference
    )

    assert report["rows"][0]["status"] == "PRESERVED_WHILE_PRIMARY_FLAT"
    assert report["rows"][0]["shares"] == 8.25
    assert float(_read(reference)[0]["shares"]) == 8.25


def test_reentry_updates_reference_to_new_primary_share_quantity(tmp_path):
    config = tmp_path / "config.json"
    current = tmp_path / "current.csv"
    reference = tmp_path / "reference.csv"
    _config(config)
    _positions(current, 8.25)
    refresh_frozen_primary_reference_quantities(
        config_path=config, current_positions_path=current, reference_path=reference
    )
    _positions(current, 9.75)

    report = refresh_frozen_primary_reference_quantities(
        config_path=config, current_positions_path=current, reference_path=reference
    )

    assert report["rows"][0]["status"] == "UPDATED_FROM_OPEN_PRIMARY"
    assert report["rows"][0]["shares"] == 9.75
    assert float(_read(reference)[0]["shares"]) == 9.75


def test_missing_initial_quantity_does_not_fabricate_reference(tmp_path):
    config = tmp_path / "config.json"
    current = tmp_path / "current.csv"
    reference = tmp_path / "reference.csv"
    _config(config)
    current.write_text("symbol,shares,market_value,cost_basis\n", encoding="utf-8")

    report = refresh_frozen_primary_reference_quantities(
        config_path=config, current_positions_path=current, reference_path=reference
    )

    assert report["rows"][0]["status"] == "MISSING_REFERENCE_QUANTITY"
    assert _read(reference) == []


def test_safety_flags_are_locked():
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert PAPER_POSITION_CREATION_ENABLED is False

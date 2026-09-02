import json
from pathlib import Path

from swing_trade_bot.frozen_primary_authority_sync import synchronize_frozen_primary_authority


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _config(path: Path) -> None:
    _write_json(path, {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "symbols": [{
            "symbol": "SOXL",
            "primary_strategy_id": "SOXL_BIGBELUGA_1H_PRIMARY",
            "shadow_strategy_ids": ["SOXL_ZERO_LAG_1H_SHADOW_1"],
            "shadow_slot_3": None,
            "research_status": "FROZEN_DEPLOYMENT_STACK",
        }],
        "strategies": [
            {
                "strategy_id": "SOXL_BIGBELUGA_1H_PRIMARY",
                "name": "SOXL BigBeluga Range Breakout 1H Primary",
                "signal_symbol": "SOXL",
                "vehicle_symbol": "SOXL",
                "timeframe": "1H",
                "engine_id": "BIGBELUGA_RANGE",
                "parameters": {"hma_entry": 0, "hma_exit": 90},
                "catastrophic_stop_percent": 20.0,
                "assignment_mode": "DIRECT",
                "enabled": True,
                "paper_trade_mode": True,
            },
            {
                "strategy_id": "SOXL_ZERO_LAG_1H_SHADOW_1",
                "name": "SOXL Zero Lag Shadow",
                "signal_symbol": "SOXL",
                "vehicle_symbol": "SOXL",
                "timeframe": "1H",
                "engine_id": "ZERO_LAG",
                "parameters": {"length": 70, "multiplier": 2.5},
                "catastrophic_stop_percent": 20.0,
                "assignment_mode": "SHADOW",
                "enabled": True,
                "paper_trade_mode": True,
            },
        ],
    })


def test_existing_position_adopts_direct_strategy_without_economic_change(tmp_path):
    config = tmp_path / "config.json"
    ledger = tmp_path / "open_positions.json"
    report_path = tmp_path / "report.json"
    _config(config)
    original = {
        "symbol": "SOXL",
        "opened_at": "2026-06-22T20:00:00+00:00",
        "entry_date": "2026-06-22",
        "entry_price": 139.9,
        "shares": 8.04145854,
        "cost_basis": 1125.0,
        "current_price": 112.79,
        "market_value": 907.0,
        "unrealized_pnl": -218.0,
        "unrealized_pnl_percent": -19.377778,
        "allocation_percent": 25.0,
        "active_strategy": "Strategy A",
        "status": "OPEN",
    }
    _write_json(ledger, {"schema_version": "1.0", "paper_trade_mode": True, "positions": [original]})

    report = synchronize_frozen_primary_authority(config_path=config, ledger_path=ledger, report_path=report_path)
    updated = json.loads(ledger.read_text(encoding="utf-8"))["positions"][0]

    assert updated["active_strategy"] == "SOXL_BIGBELUGA_1H_PRIMARY"
    assert {k: v for k, v in updated.items() if k != "active_strategy"} == {
        k: v for k, v in original.items() if k != "active_strategy"
    }
    assert report["rows"][0]["status"] == "ADOPTED"
    assert report["position_count_changed"] == 0
    assert report["share_quantity_changed"] is False
    assert report["cost_basis_changed"] is False
    assert report["paper_position_creation_enabled"] is False
    assert report["paper_position_closure_enabled"] is False


def test_sync_is_idempotent(tmp_path):
    config = tmp_path / "config.json"
    ledger = tmp_path / "open_positions.json"
    report_path = tmp_path / "report.json"
    _config(config)
    _write_json(ledger, {
        "paper_trade_mode": True,
        "positions": [{
            "symbol": "SOXL",
            "shares": 8.0,
            "cost_basis": 1000.0,
            "active_strategy": "SOXL_BIGBELUGA_1H_PRIMARY",
        }],
    })
    report = synchronize_frozen_primary_authority(config_path=config, ledger_path=ledger, report_path=report_path)
    assert report["rows"][0]["status"] == "ALREADY_ACTIVE"
    assert report["rows"][0]["position_changed"] is False


def test_missing_position_is_reported_without_fabrication(tmp_path):
    config = tmp_path / "config.json"
    ledger = tmp_path / "open_positions.json"
    report_path = tmp_path / "report.json"
    _config(config)
    _write_json(ledger, {"paper_trade_mode": True, "positions": []})

    report = synchronize_frozen_primary_authority(config_path=config, ledger_path=ledger, report_path=report_path)
    assert report["rows"][0]["status"] == "NO_OPEN_POSITION"
    assert json.loads(ledger.read_text(encoding="utf-8"))["positions"] == []


def test_shadow_never_becomes_position_authority(tmp_path):
    config = tmp_path / "config.json"
    ledger = tmp_path / "open_positions.json"
    report_path = tmp_path / "report.json"
    _config(config)
    _write_json(ledger, {
        "paper_trade_mode": True,
        "positions": [{"symbol": "SOXL", "shares": 5.0, "cost_basis": 500.0, "active_strategy": "old"}],
    })

    synchronize_frozen_primary_authority(config_path=config, ledger_path=ledger, report_path=report_path)
    active = json.loads(ledger.read_text(encoding="utf-8"))["positions"][0]["active_strategy"]
    assert active == "SOXL_BIGBELUGA_1H_PRIMARY"
    assert active != "SOXL_ZERO_LAG_1H_SHADOW_1"

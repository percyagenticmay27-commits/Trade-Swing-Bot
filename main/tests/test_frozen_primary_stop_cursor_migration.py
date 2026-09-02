import json
from pathlib import Path

import pytest

from swing_trade_bot.frozen_primary_stop_cursor_migration import migrate_missing_stop_cursors


def _write_state(path: Path, symbol_state: dict) -> None:
    path.write_text(json.dumps({
        "paper_trade_mode": True,
        "symbols": {"SOXL": symbol_state},
    }), encoding="utf-8")


def test_missing_cursor_migrates_from_original_activation_timestamp(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    _write_state(state, {
        "strategy_id": "SOXL_BIGBELUGA_1H_PRIMARY",
        "last_processed_chart_bar": "2026-09-02T13:30:00-04:00",
        "pending_signal": None,
        "allocation_notional": 1125.0,
        "initialized_at_utc": "2026-09-02T19:23:11Z",
    })

    result = migrate_missing_stop_cursors(state_path=state)

    assert result["state_changed"] is True
    assert result["rows"][0]["status"] == "MIGRATED_FROM_ACTIVATION_TIMESTAMP"
    saved = json.loads(state.read_text(encoding="utf-8"))
    row = saved["symbols"]["SOXL"]
    assert row["last_processed_stop_raw_bar"] == "2026-09-02T19:23:11Z"
    assert row["stop_cursor_migration_source"] == "ORIGINAL_PRIMARY_ACTIVATION_TIMESTAMP"


def test_existing_cursor_is_preserved_idempotently(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    _write_state(state, {
        "strategy_id": "SOXL_BIGBELUGA_1H_PRIMARY",
        "initialized_at_utc": "2026-09-02T19:23:11Z",
        "last_processed_stop_raw_bar": "2026-09-02T15:40:00-04:00",
    })
    original = state.read_text(encoding="utf-8")

    result = migrate_missing_stop_cursors(state_path=state)

    assert result["state_changed"] is False
    assert result["rows"][0]["status"] == "ALREADY_MIGRATED"
    assert state.read_text(encoding="utf-8") == original


def test_missing_activation_timestamp_fails_closed(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    _write_state(state, {
        "strategy_id": "SOXL_BIGBELUGA_1H_PRIMARY",
        "last_processed_chart_bar": "2026-09-02T13:30:00-04:00",
    })

    with pytest.raises(ValueError, match="initialized_at_utc is missing"):
        migrate_missing_stop_cursors(state_path=state)


def test_safety_flags_are_locked(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    _write_state(state, {
        "strategy_id": "SOXL_BIGBELUGA_1H_PRIMARY",
        "initialized_at_utc": "2026-09-02T19:23:11Z",
    })

    result = migrate_missing_stop_cursors(state_path=state)

    assert result["paper_trade_mode"] is True
    assert result["live_trading_enabled"] is False
    assert result["broker_execution_enabled"] is False
    assert result["order_placement_enabled"] is False
    assert result["capital_movement_enabled"] is False
    assert result["paper_position_creation_enabled"] is False
    assert result["paper_position_closure_enabled"] is False

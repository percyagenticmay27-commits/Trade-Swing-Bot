import json
from pathlib import Path
from types import SimpleNamespace

import swing_trade_bot.frozen_primary_allocation_state_sync as sync


def _write_state(path: Path, allocation_notional=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "paper_trade_mode": True,
        "symbols": {
            "NFLU": {
                "strategy_id": "NFLU_NFLX_ZERO_LAG_1H_PRIMARY",
                "signal_symbol": "NFLX",
                "vehicle_symbol": "NFLU",
                "allocation_notional": allocation_notional,
            }
        },
    }), encoding="utf-8")


def _stack():
    primary = SimpleNamespace(
        enabled=True,
        strategy_id="NFLU_NFLX_ZERO_LAG_1H_PRIMARY",
        signal_symbol="NFLX",
        vehicle_symbol="NFLU",
    )
    return SimpleNamespace(symbol="NFLU", primary=primary)


def test_missing_allocation_authority_leaves_nflu_flat_state_unchanged(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    _write_state(state)
    monkeypatch.setattr(sync, "load_frozen_symbol_stacks", lambda path: [_stack()])
    monkeypatch.setattr(sync, "resolve_frozen_primary_allocation_authority", lambda **kwargs: None)

    result = sync.synchronize_frozen_primary_allocation_state(
        config_path=tmp_path / "config.json",
        state_path=state,
        portfolio_allocation_path=tmp_path / "portfolio.json",
    )

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["symbols"]["NFLU"]["allocation_notional"] is None
    assert result["status"] == "NO_CHANGE"
    assert result["rows"][0]["status"] == "NO_SECURITY_ALLOCATION_AUTHORITY"


def test_authorized_notional_is_written_into_existing_baseline(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    _write_state(state)
    monkeypatch.setattr(sync, "load_frozen_symbol_stacks", lambda path: [_stack()])
    authority = SimpleNamespace(
        authorized_notional=675.0,
        allocation_symbol="NFLX",
        allocation_percent=15.0,
        strategy_allocated_capital=4500.0,
        row=lambda: {
            "signal_symbol": "NFLX",
            "vehicle_symbol": "NFLU",
            "allocation_symbol": "NFLX",
            "allocation_percent": 15.0,
            "strategy_allocated_capital": 4500.0,
            "authorized_notional": 675.0,
            "paper_trade_mode": True,
        },
    )
    monkeypatch.setattr(sync, "resolve_frozen_primary_allocation_authority", lambda **kwargs: authority)

    result = sync.synchronize_frozen_primary_allocation_state(
        config_path=tmp_path / "config.json",
        state_path=state,
        portfolio_allocation_path=tmp_path / "portfolio.json",
    )

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["symbols"]["NFLU"]["allocation_notional"] == 675.0
    assert saved["symbols"]["NFLU"]["allocation_authority"]["allocation_symbol"] == "NFLX"
    assert result["status"] == "UPDATED"
    assert result["rows"][0]["status"] == "AUTHORIZED_FROM_PORTFOLIO_ALLOCATION"


def test_existing_positive_reentry_notional_is_preserved_without_resolving_new_authority(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    _write_state(state, allocation_notional=500.0)
    monkeypatch.setattr(sync, "load_frozen_symbol_stacks", lambda path: [_stack()])

    def should_not_run(**kwargs):
        raise AssertionError("existing authority must be preserved")
    monkeypatch.setattr(sync, "resolve_frozen_primary_allocation_authority", should_not_run)

    result = sync.synchronize_frozen_primary_allocation_state(
        config_path=tmp_path / "config.json",
        state_path=state,
    )

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["symbols"]["NFLU"]["allocation_notional"] == 500.0
    assert result["rows"][0]["status"] == "PRESERVED_EXISTING_AUTHORITY"


def test_absent_execution_state_does_not_create_a_strategy_baseline(tmp_path):
    state = tmp_path / "missing.json"
    result = sync.synchronize_frozen_primary_allocation_state(state_path=state)
    assert result["status"] == "NO_EXECUTION_STATE"
    assert not state.exists()

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import swing_trade_bot.mapped_underlying_market_data_refresh as module


def _registry(path: Path) -> Path:
    payload = {
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mapping_policy": "EXPLICIT_VERIFIED_ONE_TO_MANY_NO_TICKER_INFERENCE",
        "review_policy": {"cadence": "WEEKLY_WEEKEND", "preferred_vehicle_scope": "FUTURE_NEW_CANDIDATES_ONLY", "existing_positions_unchanged": True, "switch_threshold_points": 5.0},
        "mappings": [
            {"underlying_symbol": "NVDA", "preferred_vehicle": "NVDX", "vehicles": [{"symbol": "NVDX", "verified": True, "enabled": True}]},
            {"underlying_symbol": "SNDK", "preferred_vehicle": "SNXX", "vehicles": [{"symbol": "SNXX", "verified": True, "enabled": True}]},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_refresh_requests_all_persistent_underlyings(monkeypatch, tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    captured = {}

    def fake_build(data_dir, **kwargs):
        captured.update(kwargs)
        summaries = tuple(
            SimpleNamespace(symbol=s, rows=100, start_date=None, end_date=None, source="yahoo", data_source="YAHOO", is_stale=False, error=None)
            for s in kwargs["symbols"]
        )
        return SimpleNamespace(summaries=summaries, validation_ok=True)

    monkeypatch.setattr(module, "build_historical_data", fake_build)
    report = module.refresh_mapped_underlying_market_data(registry_path=registry, data_dir=tmp_path)
    assert captured["symbols"] == ("NVDA", "SNDK")
    assert report["current_market_data_count"] == 2
    assert report["mapped_underlying_count"] == 2


def test_stale_or_error_market_data_is_not_current(monkeypatch, tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")

    def fake_build(data_dir, **kwargs):
        summaries = (
            SimpleNamespace(symbol="NVDA", rows=100, start_date=None, end_date=None, source="cache_stale", data_source="CACHE_STALE_FALLBACK", is_stale=True, error="provider failed"),
            SimpleNamespace(symbol="SNDK", rows=0, start_date=None, end_date=None, source=None, data_source="UNAVAILABLE", is_stale=False, error="no rows"),
        )
        return SimpleNamespace(summaries=summaries, validation_ok=False)

    monkeypatch.setattr(module, "build_historical_data", fake_build)
    report = module.refresh_mapped_underlying_market_data(registry_path=registry, data_dir=tmp_path)
    assert report["current_market_data_count"] == 0
    assert report["validation_ok"] is False
    assert all(not row["usable_for_current_quantitative_evidence"] for row in report["rows"])


def test_refresh_is_read_only_and_paper_only(monkeypatch, tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    monkeypatch.setattr(module, "build_historical_data", lambda *a, **k: SimpleNamespace(summaries=(), validation_ok=True))
    report = module.refresh_mapped_underlying_market_data(registry_path=registry, data_dir=tmp_path)
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False

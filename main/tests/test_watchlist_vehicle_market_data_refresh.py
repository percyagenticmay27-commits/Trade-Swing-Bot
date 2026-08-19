from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import swing_trade_bot.watchlist_vehicle_market_data_refresh as module
from swing_trade_bot.discovery_engine import CandidateState


def _candidate(underlying: str, vehicle: str, status: str) -> CandidateState:
    return CandidateState(
        underlying_symbol=underlying,
        leveraged_symbol=vehicle,
        status=status,  # type: ignore[arg-type]
    )


def test_only_durable_watchlist_vehicles_are_requested(monkeypatch, tmp_path: Path) -> None:
    candidates = [
        _candidate("PLTR", "PLTU", "WATCHLIST"),
        _candidate("NVDA", "NVDX", "WATCHLIST"),
        _candidate("GOOGL", "GGLL", "DISCOVERY"),
    ]
    monkeypatch.setattr(module, "load_candidate_state", lambda **kwargs: (candidates, {}))
    captured = {}

    def fake_build(data_dir, **kwargs):
        captured["symbols"] = kwargs["symbols"]
        summaries = tuple(
            SimpleNamespace(
                symbol=symbol,
                rows=100,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 8, 18),
                source="yahoo_chart",
                data_source="LIVE_PROVIDER",
                is_stale=False,
                error=None,
            )
            for symbol in kwargs["symbols"]
        )
        return SimpleNamespace(summaries=summaries, validation_ok=True)

    monkeypatch.setattr(module, "build_historical_data", fake_build)
    payload = module.refresh_watchlist_vehicle_market_data(root=tmp_path)

    assert captured["symbols"] == ("NVDX", "PLTU", "SPY", "QQQ")
    assert payload["watchlist_vehicles"] == ["NVDX", "PLTU"]
    assert payload["watchlist_vehicle_count"] == 2


def test_stale_or_error_rows_are_not_entry_usable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        module,
        "load_candidate_state",
        lambda **kwargs: ([_candidate("PLTR", "PLTU", "WATCHLIST")], {}),
    )
    summaries = (
        SimpleNamespace(symbol="PLTU", rows=100, start_date=None, end_date=None, source="cache_stale", data_source="CACHE_STALE_FALLBACK", is_stale=True, error="provider failed"),
        SimpleNamespace(symbol="SPY", rows=100, start_date=None, end_date=None, source="yahoo", data_source="LIVE_PROVIDER", is_stale=False, error=None),
        SimpleNamespace(symbol="QQQ", rows=100, start_date=None, end_date=None, source="yahoo", data_source="LIVE_PROVIDER", is_stale=False, error=None),
    )
    monkeypatch.setattr(module, "build_historical_data", lambda *args, **kwargs: SimpleNamespace(summaries=summaries, validation_ok=False))
    payload = module.refresh_watchlist_vehicle_market_data(root=tmp_path)
    vehicle = next(row for row in payload["rows"] if row["symbol"] == "PLTU")
    assert vehicle["usable_for_entry_evaluation"] is False
    assert payload["validation_ok"] is False


def test_market_refresh_is_read_only_and_paper_only(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "load_candidate_state", lambda **kwargs: ([], {}))
    monkeypatch.setattr(module, "build_historical_data", lambda *args, **kwargs: SimpleNamespace(summaries=(), validation_ok=True))
    payload = module.refresh_watchlist_vehicle_market_data(root=tmp_path)
    assert payload["paper_trade_mode"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["broker_execution_enabled"] is False
    assert payload["order_placement_enabled"] is False
    assert payload["capital_movement_enabled"] is False

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import swing_trade_bot.watchlist_entry_evaluation as module
from swing_trade_bot.discovery_engine import CandidateState


def _candidate(underlying: str, vehicle: str, status: str = "WATCHLIST") -> CandidateState:
    return CandidateState(
        underlying_symbol=underlying,
        leveraged_symbol=vehicle,
        status=status,  # type: ignore[arg-type]
    )


def test_only_watchlist_candidates_enter_timing_evaluation(monkeypatch, tmp_path: Path) -> None:
    candidates = [
        _candidate("PLTR", "PLTU"),
        _candidate("NVDA", "NVDX"),
        _candidate("GOOGL", "GGLL", "DISCOVERY"),
    ]
    monkeypatch.setattr(module, "load_candidate_state", lambda **kwargs: (candidates, {}))
    monkeypatch.setattr(module, "load_veto_ledger", lambda path: {"strategy_id": "SWING-001", "paper_trade_mode": True, "approval_required": False, "events": []})
    monkeypatch.setattr(module, "active_vetoes", lambda payload: {})
    monkeypatch.setattr(module, "load_csv", lambda path: [SimpleNamespace()] * 60)

    captured = {}

    class FakeEngine:
        def __init__(self, config, **kwargs):
            captured["symbols"] = config.symbols
            captured["map"] = config.underlying_exposure_map
        def evaluate(self, symbol, bars, benchmark_data=None, earnings_dates=None):
            return SimpleNamespace(signal="HOLD", reason="No entry", current_price=10.0)

    monkeypatch.setattr(module, "SwingTradeEngine", FakeEngine)
    data = tmp_path / "data"
    data.mkdir()
    for symbol in ("PLTU", "NVDX", "SPY", "QQQ"):
        (data / f"{symbol}.csv").write_text("stub", encoding="utf-8")

    payload = module.evaluate_watchlist_entries(root=tmp_path)
    assert captured["symbols"] == ("NVDX", "PLTU")
    assert captured["map"] == (("NVDA", "NVDX"), ("PLTR", "PLTU"))
    assert {row["vehicle_symbol"] for row in payload["rows"]} == {"NVDX", "PLTU"}
    assert payload["watchlist_vehicle_count"] == 2


def test_engine_buy_becomes_entry_ready_evidence_only(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "load_candidate_state", lambda **kwargs: ([_candidate("PLTR", "PLTU")], {}))
    monkeypatch.setattr(module, "load_veto_ledger", lambda path: {"strategy_id": "SWING-001", "paper_trade_mode": True, "approval_required": False, "events": []})
    monkeypatch.setattr(module, "active_vetoes", lambda payload: {})
    monkeypatch.setattr(module, "load_csv", lambda path: [SimpleNamespace()] * 60)

    class FakeEngine:
        def __init__(self, **kwargs):
            pass
        def evaluate(self, *args, **kwargs):
            return SimpleNamespace(signal="BUY", reason="All initial entry conditions are met", current_price=20.0)

    monkeypatch.setattr(module, "SwingTradeEngine", FakeEngine)
    data = tmp_path / "data"
    data.mkdir()
    for symbol in ("PLTU", "SPY", "QQQ"):
        (data / f"{symbol}.csv").write_text("stub", encoding="utf-8")

    payload = module.evaluate_watchlist_entries(root=tmp_path)
    row = payload["rows"][0]
    assert row["evaluation_status"] == "ENTRY_READY"
    assert row["entry_ready"] is True
    assert row["paper_position_created"] is False
    assert payload["paper_positions_created"] == 0
    assert payload["paper_ledger_written"] is False
    assert payload["numeric_entry_score_invented"] is False


def test_active_veto_blocks_entry_evaluation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "load_candidate_state", lambda **kwargs: ([_candidate("PLTR", "PLTU")], {}))
    monkeypatch.setattr(module, "load_veto_ledger", lambda path: {"strategy_id": "SWING-001", "paper_trade_mode": True, "approval_required": False, "events": []})
    monkeypatch.setattr(module, "active_vetoes", lambda payload: {"PLTR": {"action": "VETO"}})
    payload = module.evaluate_watchlist_entries(root=tmp_path)
    assert payload["rows"][0]["evaluation_status"] == "VETO_BLOCKED"
    assert payload["rows"][0]["entry_ready"] is False


def test_missing_vehicle_history_fails_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "load_candidate_state", lambda **kwargs: ([_candidate("PLTR", "PLTU")], {}))
    monkeypatch.setattr(module, "load_veto_ledger", lambda path: {"strategy_id": "SWING-001", "paper_trade_mode": True, "approval_required": False, "events": []})
    monkeypatch.setattr(module, "active_vetoes", lambda payload: {})
    payload = module.evaluate_watchlist_entries(root=tmp_path)
    assert payload["rows"][0]["evaluation_status"] == "MISSING_MARKET_DATA"
    assert payload["rows"][0]["entry_ready"] is False


def test_known_earnings_dates_are_passed_to_existing_engine(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "load_candidate_state", lambda **kwargs: ([_candidate("PLTR", "PLTU")], {}))
    monkeypatch.setattr(module, "load_veto_ledger", lambda path: {"strategy_id": "SWING-001", "paper_trade_mode": True, "approval_required": False, "events": []})
    monkeypatch.setattr(module, "active_vetoes", lambda payload: {})
    monkeypatch.setattr(module, "load_csv", lambda path: [SimpleNamespace()] * 60)
    results = tmp_path / "results"
    results.mkdir()
    (results / "earnings_report.json").write_text(json.dumps({"rows": [{"symbol": "PLTR", "earnings_date": "2026-08-25"}]}), encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    for symbol in ("PLTU", "SPY", "QQQ"):
        (data / f"{symbol}.csv").write_text("stub", encoding="utf-8")
    captured = {}

    class FakeEngine:
        def __init__(self, **kwargs):
            pass
        def evaluate(self, symbol, bars, benchmark_data=None, earnings_dates=None):
            captured["earnings"] = earnings_dates
            return SimpleNamespace(signal="HOLD", reason="blocked", current_price=20.0)

    monkeypatch.setattr(module, "SwingTradeEngine", FakeEngine)
    payload = module.evaluate_watchlist_entries(root=tmp_path)
    assert str(captured["earnings"]["PLTR"]) == "2026-08-25"
    assert payload["rows"][0]["earnings_date_known"] is True


def test_output_is_paper_only_and_no_execution(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "load_candidate_state", lambda **kwargs: ([], {}))
    monkeypatch.setattr(module, "load_veto_ledger", lambda path: {"strategy_id": "SWING-001", "paper_trade_mode": True, "approval_required": False, "events": []})
    monkeypatch.setattr(module, "active_vetoes", lambda payload: {})
    payload = module.evaluate_watchlist_entries(root=tmp_path)
    assert payload["paper_trade_mode"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["broker_execution_enabled"] is False
    assert payload["order_placement_enabled"] is False
    assert payload["capital_movement_enabled"] is False
    assert payload["paper_positions_created"] == 0
    assert payload["paper_ledger_written"] is False

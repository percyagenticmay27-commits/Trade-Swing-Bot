from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot import swing_daily_cycle as cycle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_refresh_rebuilds_closed_trades_before_governed_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = tmp_path / "results"
    ledger = results / "paper_ledger"
    data = tmp_path / "data"
    results.mkdir()
    ledger.mkdir()
    data.mkdir()

    (results / "strategy_recommendations.csv").write_text(
        "symbol,active_strategy\nNFLX,Strategy A\n",
        encoding="utf-8",
    )
    _write_json(results / "watchlist_report.json", {"rows": []})
    _write_json(ledger / "open_positions.json", {"paper_trade_mode": True, "positions": []})
    _write_json(ledger / "trade_history.json", {"paper_trade_mode": True, "trades": []})

    calls: list[str] = []

    def trade_history(**kwargs):
        calls.append("trade_history")
        assert kwargs["data_dir"] == data
        _write_json(ledger / "managed_trade_history.json", {"paper_trade_mode": True})
        _write_json(ledger / "closed_positions.json", {"paper_trade_mode": True, "closed_trades": []})
        _write_json(ledger / "trade_history_summary.json", {"paper_trade_mode": True})

    def governed(**kwargs):
        calls.append("governed_allocation")
        assert (ledger / "closed_positions.json").is_file()
        assert kwargs["results_dir"] == results
        assert kwargs["ledger_dir"] == ledger
        assert kwargs["data_dir"] == data
        assert kwargs["config_path"] == tmp_path / "configs/frozen_strategy_assignments.json"
        assert kwargs["strategy_recommendations_path"] == results / "strategy_recommendations.csv"
        assert kwargs["paper_trade_mode"] is True
        return {
            "schema_version": "1.0",
            "strategy_id": "SWING-001",
            "paper_trade_mode": True,
            "governed_allocation_symbols": [],
            "allocation_row_count": 0,
            "sgov_allocation": 100.0,
            "allocation_bypass_allowed": False,
        }

    def paper_portfolio(**kwargs):
        calls.append("paper_portfolio")
        _write_json(ledger / "paper_portfolio_summary.json", {"paper_trade_mode": True})
        _write_json(
            ledger / "paper_portfolio_positions.json",
            {"paper_trade_mode": True, "position_count": 0, "positions": []},
        )

    def performance(**kwargs):
        calls.append("performance")

    monkeypatch.setattr(cycle, "build_and_write_trade_history_report", trade_history)
    monkeypatch.setattr(cycle, "refresh_forward_confidence_and_governed_allocation", governed)
    monkeypatch.setattr(cycle, "build_and_write_paper_portfolio_report", paper_portfolio)
    monkeypatch.setattr(cycle, "build_and_write_performance_analytics_report", performance)
    monkeypatch.setattr(cycle, "load_discovered_strategy_allocations", lambda: ({}, tmp_path / "enterprise.json"))
    monkeypatch.setattr(
        cycle,
        "resolve_strategy_allocation_evidence",
        lambda payload, strategy_id: {
            "allocated_capital": 4500.0,
            "allocation_source_json_path": "strategies.SWING-001",
            "allocation_evidence_schema": "test",
        },
    )

    refresh = {
        "portfolio_allocation": {
            "confidence_path": "results/confidence_report.csv",
            "strategy_recommendations_path": "results/strategy_recommendations.csv",
        },
        "paper_ledger": {
            "ledger_dir": "results/paper_ledger",
            "data_dir": "data",
            "max_price_age_days": 5,
        },
    }
    published: list[str] = []
    cycle._refresh_allocation_and_paper_evidence(
        tmp_path,
        results,
        refresh,
        "2026-09-02T23:00:00Z",
        published,
    )

    assert calls == ["trade_history", "governed_allocation", "paper_portfolio", "performance"]
    assert (results / "governed_allocation_bridge.json").is_file()
    summary = json.loads((results / "governed_allocation_bridge.json").read_text(encoding="utf-8"))
    assert summary["allocation_bypass_allowed"] is False
    assert str(results / "confidence_report.json") in published
    assert str(results / "committee_allocation_eligibility.json") in published
    assert str(results / "portfolio_allocations.json") in published


def test_daily_cycle_no_longer_imports_direct_portfolio_allocator() -> None:
    assert not hasattr(cycle, "build_portfolio_allocation_report")

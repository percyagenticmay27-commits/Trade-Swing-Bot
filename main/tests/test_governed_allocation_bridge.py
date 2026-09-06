import csv
import json
from pathlib import Path

import pytest

from swing_trade_bot.governed_allocation_bridge import refresh_forward_confidence_and_governed_allocation


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _base(tmp_path: Path, *, oq: float, entry: float | None, thesis: bool | None) -> tuple[Path, Path, Path, Path]:
    results = tmp_path / "results"
    ledger = results / "paper_ledger"
    data = tmp_path / "data"
    config = tmp_path / "frozen.json"
    results.mkdir()
    ledger.mkdir()
    data.mkdir()
    _write_json(config, {
        "strategy_id": "SWING-001", "paper_trade_mode": True,
        "symbols": [{"symbol": "NFLU", "primary_strategy_id": "NFLU_PRIMARY", "shadow_strategy_ids": [], "shadow_slot_3": None}],
        "strategies": [{
            "strategy_id": "NFLU_PRIMARY", "name": "NFLU Primary", "signal_symbol": "NFLX", "vehicle_symbol": "NFLU",
            "timeframe": "1H", "engine_id": "ZERO_LAG", "parameters": {"length": 50, "multiplier": 2.5},
            "assignment_mode": "DIRECT", "enabled": True, "paper_trade_mode": True,
        }],
    })
    _write_json(results / "watchlist_report.json", {"rows": [{
        "underlying_symbol": "NFLX", "leveraged_symbol": "NFLU", "capacity_status": "ACTIVE", "watchlist_status": "HIGH",
        "watchlist_rank": 1, "themes": "Cloud Computing"
    }]})
    quality = {"symbol": "NFLX", "opportunity_quality_score": oq}
    if entry is not None:
        quality["entry_score"] = entry
    if thesis is not None:
        quality["thesis_intact"] = thesis
    _write_json(results / "opportunity_quality_report.json", {"rows": [quality]})
    _write_json(ledger / "closed_positions.json", {"paper_trade_mode": True, "closed_trades": []})
    _write_csv(results / "strategy_recommendations.csv", ["symbol", "active_strategy"], [{"symbol": "NFLX", "active_strategy": "Legacy Strategy A"}])
    return results, ledger, data, config


def test_ineligible_candidate_cannot_enter_allocation_even_with_high_watchlist_status(tmp_path: Path) -> None:
    results, ledger, data, config = _base(tmp_path, oq=68.2305, entry=99, thesis=True)
    summary = refresh_forward_confidence_and_governed_allocation(
        results_dir=results, ledger_dir=ledger, data_dir=data, config_path=config,
        strategy_recommendations_path=results / "strategy_recommendations.csv",
    )
    assert summary["eligible_symbols"] == []
    assert summary["governed_allocation_symbols"] == []
    assert summary["sgov_allocation"] == 100.0
    payload = json.loads((results / "portfolio_allocations.json").read_text(encoding="utf-8"))
    assert [row["symbol"] for row in payload["allocations"]] == ["SGOV"]


def test_eligible_candidate_with_explicit_forward_confidence_can_allocate(tmp_path: Path) -> None:
    results, ledger, data, config = _base(tmp_path, oq=82, entry=75, thesis=True)
    summary = refresh_forward_confidence_and_governed_allocation(
        results_dir=results, ledger_dir=ledger, data_dir=data, config_path=config,
        strategy_recommendations_path=results / "strategy_recommendations.csv",
    )
    assert summary["eligible_symbols"] == ["NFLX"]
    assert summary["forward_confidence_symbols"] == ["NFLX"]
    assert summary["governed_allocation_symbols"] == ["NFLX"]
    assert summary["allocation_strategy_authority"] == "CURRENT_FROZEN_PRIMARY"
    payload = json.loads((results / "portfolio_allocations.json").read_text(encoding="utf-8"))
    nflx = next(row for row in payload["allocations"] if row["symbol"] == "NFLX")
    assert nflx["confidence_level"] == "LOW"
    assert nflx["allocation_percent"] == 7.0
    assert nflx["active_strategy"] == "NFLU_PRIMARY"


def test_legacy_strategy_recommendation_cannot_override_frozen_primary(tmp_path: Path) -> None:
    results, ledger, data, config = _base(tmp_path, oq=82, entry=75, thesis=True)
    refresh_forward_confidence_and_governed_allocation(
        results_dir=results, ledger_dir=ledger, data_dir=data, config_path=config,
        strategy_recommendations_path=results / "strategy_recommendations.csv",
    )
    payload = json.loads((results / "portfolio_allocations.json").read_text(encoding="utf-8"))
    nflx = next(row for row in payload["allocations"] if row["symbol"] == "NFLX")
    assert nflx["active_strategy"] == "NFLU_PRIMARY"
    assert nflx["active_strategy"] != "Legacy Strategy A"


def test_legacy_confidence_artifact_is_not_used_as_forward_starting_state(tmp_path: Path) -> None:
    results, ledger, data, config = _base(tmp_path, oq=82, entry=75, thesis=True)
    _write_json(results / "confidence_report.json", {
        "paper_trade_mode": True,
        "rows": [{"symbol": "NFLX", "confidence": "HIGH"}],
    })
    refresh_forward_confidence_and_governed_allocation(
        results_dir=results, ledger_dir=ledger, data_dir=data, config_path=config,
        strategy_recommendations_path=results / "strategy_recommendations.csv",
    )
    payload = json.loads((results / "confidence_report.json").read_text(encoding="utf-8"))
    nflx = next(row for row in payload["rows"] if row["symbol"] == "NFLX")
    assert nflx["confidence"] == "LOW"


def test_missing_entry_score_produces_no_allocation(tmp_path: Path) -> None:
    results, ledger, data, config = _base(tmp_path, oq=82, entry=None, thesis=True)
    summary = refresh_forward_confidence_and_governed_allocation(
        results_dir=results, ledger_dir=ledger, data_dir=data, config_path=config,
        strategy_recommendations_path=results / "strategy_recommendations.csv",
    )
    assert summary["eligible_symbols"] == []
    assert summary["sgov_allocation"] == 100.0


def test_live_mode_rejected(tmp_path: Path) -> None:
    results, ledger, data, config = _base(tmp_path, oq=82, entry=75, thesis=True)
    with pytest.raises(ValueError):
        refresh_forward_confidence_and_governed_allocation(
            results_dir=results, ledger_dir=ledger, data_dir=data, config_path=config,
            strategy_recommendations_path=results / "strategy_recommendations.csv",
            paper_trade_mode=False,
        )

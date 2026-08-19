from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.mapped_underlying_portfolio_risk_evidence import (
    build_mapped_underlying_portfolio_risk_evidence,
    score_candidate_portfolio_risk,
)


def _registry(path: Path) -> Path:
    payload = {
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mapping_policy": "EXPLICIT_VERIFIED_ONE_TO_MANY_NO_TICKER_INFERENCE",
        "review_policy": {"cadence": "WEEKLY_WEEKEND", "preferred_vehicle_scope": "FUTURE_NEW_CANDIDATES_ONLY", "existing_positions_unchanged": True, "switch_threshold_points": 5.0},
        "mappings": [{"underlying_symbol": "NVDA", "preferred_vehicle": "NVDX", "vehicles": [{"symbol": "NVDX", "verified": True, "enabled": True}]}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_empty_portfolio_is_maximally_supportive_for_new_candidate() -> None:
    result = score_candidate_portfolio_risk(preferred_vehicle="NVDX", positions=[])
    assert result["portfolio_risk_adjustment_score"] == 100.0
    assert result["duplicate_position"] is False


def test_duplicate_position_reduces_support() -> None:
    result = score_candidate_portfolio_risk(
        preferred_vehicle="NVDX",
        positions=[{"symbol": "NVDX", "allocation_percent": 20.0}],
    )
    assert result["duplicate_position"] is True
    assert result["portfolio_risk_adjustment_score"] < 100.0


def test_high_concentration_reduces_support() -> None:
    result = score_candidate_portfolio_risk(
        preferred_vehicle="NVDX",
        positions=[{"symbol": "SOXL", "allocation_percent": 55.0}, {"symbol": "TQQQ", "allocation_percent": 20.0}],
    )
    assert result["portfolio_risk_adjustment_score"] <= 60.0
    assert result["max_existing_allocation_percent"] == 55.0


def test_missing_portfolio_evidence_fails_closed(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_portfolio_risk_evidence(registry_path=registry, results_dir=tmp_path)
    row = report["rows"][0]
    assert row["portfolio_risk_adjustment_score"] is None
    assert row["evidence_status"] == "MISSING_PAPER_PORTFOLIO_EVIDENCE"


def test_portfolio_risk_is_paper_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    positions = tmp_path / "positions.json"
    positions.write_text(json.dumps({"positions": []}), encoding="utf-8")
    report = build_mapped_underlying_portfolio_risk_evidence(
        registry_path=registry, results_dir=tmp_path, positions_path=positions
    )
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False
    assert report["capital_movement_enabled"] is False

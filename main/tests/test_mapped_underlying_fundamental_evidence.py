from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.mapped_underlying_fundamental_evidence import (
    build_mapped_underlying_fundamental_evidence,
    score_fundamental_metrics,
    write_mapped_underlying_fundamental_evidence,
)


def _registry(path: Path) -> Path:
    payload = {
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mapping_policy": "EXPLICIT_VERIFIED_ONE_TO_MANY_NO_TICKER_INFERENCE",
        "review_policy": {
            "cadence": "WEEKLY_WEEKEND",
            "preferred_vehicle_scope": "FUTURE_NEW_CANDIDATES_ONLY",
            "existing_positions_unchanged": True,
            "switch_threshold_points": 5.0,
        },
        "mappings": [
            {
                "underlying_symbol": "NVDA",
                "preferred_vehicle": "NVDX",
                "vehicles": [{"symbol": "NVDX", "verified": True, "enabled": True}],
            },
            {
                "underlying_symbol": "SNDK",
                "preferred_vehicle": "SNXX",
                "vehicles": [{"symbol": "SNXX", "verified": True, "enabled": True}],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_strong_company_metrics_generate_bounded_high_score() -> None:
    result = score_fundamental_metrics(
        {
            "revenue_growth_pct": 25,
            "earnings_growth_pct": 35,
            "operating_margin_pct": 30,
            "free_cash_flow_margin_pct": 24,
            "return_on_equity_pct": 35,
            "current_ratio": 1.8,
            "debt_to_equity": 0.4,
        }
    )
    assert result is not None
    assert 0 <= result["fundamental_analysis_score"] <= 100
    assert result["fundamental_analysis_score"] >= 75
    assert result["metric_count"] == 7


def test_fewer_than_four_raw_metrics_fail_closed() -> None:
    result = score_fundamental_metrics(
        {"revenue_growth_pct": 20, "operating_margin_pct": 25, "current_ratio": 1.4}
    )
    assert result is None


def test_mapped_universe_scores_underlying_not_vehicle(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_fundamental_evidence(
        registry_path=registry,
        metric_rows=[
            {
                "underlying_symbol": "NVDA",
                "revenue_growth_pct": 20,
                "earnings_growth_pct": 30,
                "operating_margin_pct": 25,
                "free_cash_flow_margin_pct": 20,
            },
            {
                "underlying_symbol": "NVDX",
                "revenue_growth_pct": 99,
                "earnings_growth_pct": 99,
                "operating_margin_pct": 99,
                "free_cash_flow_margin_pct": 99,
            },
        ],
    )
    nvda = next(row for row in report["rows"] if row["underlying_symbol"] == "NVDA")
    assert nvda["preferred_vehicle"] == "NVDX"
    assert nvda["evidence_status"] == "AVAILABLE"
    assert report["fundamentally_scored_count"] == 1


def test_ai_cio_status_and_entry_score_do_not_create_fundamental_score(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_fundamental_evidence(
        registry_path=registry,
        metric_rows=[
            {"underlying_symbol": "NVDA", "discovery_status": "HOT", "entry_score": 99}
        ],
    )
    nvda = next(row for row in report["rows"] if row["underlying_symbol"] == "NVDA")
    assert nvda["fundamental_analysis_score"] is None
    assert report["ai_cio_discovery_status_used_as_score"] is False
    assert report["entry_score_used_as_fundamental_evidence"] is False


def test_write_is_atomic_and_paper_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_fundamental_evidence(registry_path=registry, metric_rows=[])
    path = write_mapped_underlying_fundamental_evidence(report, output_dir=tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["paper_trade_mode"] is True
    assert saved["live_trading_enabled"] is False
    assert saved["broker_execution_enabled"] is False
    assert saved["order_placement_enabled"] is False

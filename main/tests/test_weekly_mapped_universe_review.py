from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.weekly_mapped_universe_review import (
    build_weekly_mapped_universe_review,
    write_weekly_mapped_universe_review,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _registry(path: Path) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "2.0",
            "strategy_id": "SWING-001",
            "mappings": [
                {
                    "underlying_symbol": "NVDA",
                    "preferred_vehicle": "NVDX",
                    "vehicles": [{"symbol": "NVDX", "enabled": True, "verified": True}],
                },
                {
                    "underlying_symbol": "PLTR",
                    "preferred_vehicle": "PLTU",
                    "vehicles": [{"symbol": "PLTU", "enabled": True, "verified": True}],
                },
                {
                    "underlying_symbol": "SNDK",
                    "preferred_vehicle": "SNXX",
                    "vehicles": [{"symbol": "SNXX", "enabled": True, "verified": True}],
                },
            ],
        },
    )


def _swing_evidence(path: Path) -> Path:
    return _write_json(
        path,
        {
            "rows": [
                {
                    "symbol": "NVDA",
                    "fundamental_analysis_score": 95,
                    "market_intelligence_score": 92,
                    "conviction_score": 94,
                    "momentum_score": 90,
                    "technical_analysis_score": 88,
                    "market_regime_support_score": 80,
                    "portfolio_risk_adjustment_score": 85,
                    "entry_score": 10,
                },
                {
                    "symbol": "PLTR",
                    "fundamental_analysis_score": 82,
                    "market_intelligence_score": 84,
                    "conviction_score": 80,
                    "momentum_score": 86,
                    "technical_analysis_score": 79,
                    "market_regime_support_score": 75,
                    "portfolio_risk_adjustment_score": 78,
                    "entry_score": 99,
                },
            ]
        },
    )


def test_persistent_mapping_universe_is_reviewed_without_ai_cio_bucket(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    evidence = _swing_evidence(tmp_path / "swing_scores.json")

    report = build_weekly_mapped_universe_review(
        registry_path=registry,
        results_dir=tmp_path,
        source_paths=[evidence],
        generated_at_utc="2026-08-19T15:00:00Z",
    )

    assert report["mapped_underlying_count"] == 3
    assert {row["underlying_symbol"] for row in report["rows"]} == {"NVDA", "PLTR", "SNDK"}
    assert next(row for row in report["rows"] if row["underlying_symbol"] == "SNDK")["preferred_vehicle"] == "SNXX"


def test_frozen_opportunity_quality_ranks_mapped_underlyings_and_entry_is_display_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    evidence = _swing_evidence(tmp_path / "swing_scores.json")

    report = build_weekly_mapped_universe_review(
        registry_path=registry,
        results_dir=tmp_path,
        source_paths=[evidence],
        generated_at_utc="2026-08-19T15:00:00Z",
    )

    assert report["ranking_authority"] == "FROZEN_OPPORTUNITY_QUALITY_ENGINE_V1_2"
    assert report["ai_cio_discovery_status_used_in_ranking"] is False
    assert report["entry_score_used_in_ranking"] is False
    assert report["entry_score_used_for_watchlist_selection"] is False
    assert report["rows"][0]["underlying_symbol"] == "NVDA"
    assert report["rows"][0]["entry_score"] == 10
    assert report["rows"][0]["selected_for_watchlist"] is True


def test_only_quality_eligible_names_fill_up_to_configured_maximum(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    evidence = _swing_evidence(tmp_path / "swing_scores.json")

    report = build_weekly_mapped_universe_review(
        registry_path=registry,
        results_dir=tmp_path,
        source_paths=[evidence],
        max_watchlist_size=1,
    )

    assert report["selected_watchlist_count"] == 1
    assert report["selected_underlyings"] == ["NVDA"]
    sndk = next(row for row in report["rows"] if row["underlying_symbol"] == "SNDK")
    assert sndk["opportunity_quality_score"] == 0
    assert sndk["selected_for_watchlist"] is False


def test_report_writes_json_csv_and_markdown_without_execution(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    evidence = _swing_evidence(tmp_path / "swing_scores.json")
    report = build_weekly_mapped_universe_review(
        registry_path=registry,
        results_dir=tmp_path,
        source_paths=[evidence],
    )
    paths = write_weekly_mapped_universe_review(report, output_dir=tmp_path / "results")

    assert all(path.is_file() for path in paths)
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False

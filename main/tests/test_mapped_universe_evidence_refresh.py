from __future__ import annotations

import json
from pathlib import Path

from swing_trade_bot.mapped_universe_evidence_refresh import (
    build_mapped_universe_evidence_refresh,
    write_mapped_universe_evidence_refresh,
)


def _registry(path: Path) -> Path:
    payload = {
        "schema_version": "1.0",
        "underlyings": {
            "NVDA": {
                "preferred_vehicle": "NVDX",
                "vehicles": [{"symbol": "NVDX", "verified": True, "enabled": True}],
            },
            "SNDK": {
                "preferred_vehicle": "SNXX",
                "vehicles": [{"symbol": "SNXX", "verified": True, "enabled": True}],
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_refresh_reviews_persistent_mapping_without_ai_cio_bucket(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    source = tmp_path / "evidence.json"
    source.write_text(
        json.dumps({"rows": [{"symbol": "NVDA", "fundamental_analysis_score": 88}]}),
        encoding="utf-8",
    )
    report = build_mapped_universe_evidence_refresh(
        registry_path=registry,
        results_dir=tmp_path,
        source_paths=[source],
        generated_at_utc="2026-08-18T23:30:00Z",
    )
    assert report["mapped_underlying_count"] == 2
    assert [row["underlying_symbol"] for row in report["rows"]] == ["NVDA", "SNDK"]
    assert report["ai_cio_discovery_status_used_as_score"] is False


def test_refresh_preserves_missing_components_as_missing_evidence(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    source = tmp_path / "evidence.json"
    source.write_text(
        json.dumps({"rows": [{"symbol": "NVDA", "fundamental_analysis_score": 88}]}),
        encoding="utf-8",
    )
    report = build_mapped_universe_evidence_refresh(
        registry_path=registry, results_dir=tmp_path, source_paths=[source]
    )
    nvda = next(row for row in report["rows"] if row["underlying_symbol"] == "NVDA")
    assert nvda["component_evidence_count"] == 1
    assert nvda["component_evidence_complete"] is False
    assert nvda["component_scores"]["fundamental_analysis_score"] == 88.0
    assert nvda["component_scores"]["market_intelligence_score"] is None


def test_refresh_does_not_treat_entry_score_as_component(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    source = tmp_path / "evidence.json"
    source.write_text(
        json.dumps({"rows": [{"symbol": "NVDA", "entry_score": 99}]}), encoding="utf-8"
    )
    report = build_mapped_universe_evidence_refresh(
        registry_path=registry, results_dir=tmp_path, source_paths=[source]
    )
    nvda = next(row for row in report["rows"] if row["underlying_symbol"] == "NVDA")
    assert nvda["component_evidence_count"] == 0
    assert "entry_score" not in nvda["component_scores"]
    assert report["entry_score_used_as_opportunity_quality_component"] is False


def test_refresh_write_is_atomic_and_paper_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_universe_evidence_refresh(
        registry_path=registry, results_dir=tmp_path, source_paths=[]
    )
    path = write_mapped_universe_evidence_refresh(report, output_dir=tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["paper_trade_mode"] is True
    assert saved["live_trading_enabled"] is False
    assert saved["broker_execution_enabled"] is False
    assert saved["order_placement_enabled"] is False


def test_module_exposes_no_broker_or_order_execution_path() -> None:
    import swing_trade_bot.mapped_universe_evidence_refresh as module

    names = {name.lower() for name in vars(module)}
    assert not any(name.startswith("place_order") for name in names)
    assert not any(name.startswith("execute_trade") for name in names)
    assert not any(name.startswith("submit_order") for name in names)

from __future__ import annotations

import csv
import json
from pathlib import Path

from swing_trade_bot.mapped_underlying_quantitative_evidence import (
    build_mapped_underlying_quantitative_evidence,
    score_quantitative_evidence,
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


def _rows(count: int = 60, rising: bool = True):
    rows = []
    for i in range(count):
        close = 100 + i if rising else 160 - i
        rows.append({"date": f"2026-01-{(i % 28) + 1:02d}", "close": float(close), "volume": float(1_000_000 + i * 10_000)})
    return rows


def test_rising_history_generates_bounded_momentum_and_technical_scores() -> None:
    result = score_quantitative_evidence(_rows())
    assert result is not None
    assert 0 <= result["momentum_score"] <= 100
    assert 0 <= result["technical_analysis_score"] <= 100
    assert result["momentum_score"] > 50
    assert result["technical_analysis_score"] > 50


def test_insufficient_history_generates_no_scores() -> None:
    assert score_quantitative_evidence(_rows(49)) is None


def test_mapped_underlying_missing_csv_fails_closed(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_quantitative_evidence(registry_path=registry, data_dir=tmp_path)
    row = report["rows"][0]
    assert row["momentum_score"] is None
    assert row["technical_analysis_score"] is None
    assert row["evidence_status"] == "MISSING_OR_INSUFFICIENT_OHLCV"


def test_mapped_underlying_csv_generates_only_quantitative_components(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    path = tmp_path / "NVDA.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for i in range(60):
            close = 100 + i
            writer.writerow({"date": f"2026-01-{(i % 28) + 1:02d}", "open": close - 1, "high": close + 1, "low": close - 2, "close": close, "volume": 1_000_000 + i * 10_000})
    report = build_mapped_underlying_quantitative_evidence(registry_path=registry, data_dir=tmp_path)
    row = report["rows"][0]
    assert row["evidence_status"] == "AVAILABLE"
    assert row["momentum_score"] is not None
    assert row["technical_analysis_score"] is not None
    assert "fundamental_analysis_score" not in row
    assert "market_intelligence_score" not in row
    assert report["ai_cio_discovery_status_used_as_score"] is False


def test_quantitative_evidence_is_paper_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_quantitative_evidence(registry_path=registry, data_dir=tmp_path)
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False

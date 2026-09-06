from __future__ import annotations

import csv
import json
from pathlib import Path

from swing_trade_bot.mapped_underlying_market_regime_evidence import (
    build_mapped_underlying_market_regime_evidence,
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


def _write_history(path: Path, rising: bool) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for i in range(60):
            close = 100 + i if rising else 160 - i
            writer.writerow({"date": f"2026-01-{(i % 28) + 1:02d}", "open": close, "high": close, "low": close, "close": close, "volume": 1_000_000})


def test_positive_spy_and_qqq_regime_generates_high_support(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    _write_history(tmp_path / "SPY.csv", True)
    _write_history(tmp_path / "QQQ.csv", True)
    report = build_mapped_underlying_market_regime_evidence(registry_path=registry, data_dir=tmp_path)
    assert report["market_regime_support_score"] == 100.0
    assert report["rows"][0]["market_regime_support_score"] == 100.0


def test_mixed_regime_is_partial_support(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    _write_history(tmp_path / "SPY.csv", True)
    _write_history(tmp_path / "QQQ.csv", False)
    report = build_mapped_underlying_market_regime_evidence(registry_path=registry, data_dir=tmp_path)
    assert report["market_regime_support_score"] == 50.0


def test_missing_benchmark_fails_closed(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    _write_history(tmp_path / "SPY.csv", True)
    report = build_mapped_underlying_market_regime_evidence(registry_path=registry, data_dir=tmp_path)
    assert report["market_regime_support_score"] is None
    assert report["rows"][0]["market_regime_support_score"] is None
    assert "QQQ" in report["missing_benchmarks"]


def test_market_regime_is_paper_only_and_ai_cio_independent(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_market_regime_evidence(registry_path=registry, data_dir=tmp_path)
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False
    assert report["ai_cio_discovery_status_used_as_score"] is False

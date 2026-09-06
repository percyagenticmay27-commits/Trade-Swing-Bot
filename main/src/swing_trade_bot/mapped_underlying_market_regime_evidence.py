"""Swing-owned Market Regime Support evidence for mapped underlyings.

This module uses broad-market daily history only. It does not inspect AI CIO
status, news labels, entry score, or broker data. A regime score is published
only when both SPY and QQQ have sufficient local daily history.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping

from .leveraged_vehicle_registry import preferred_vehicle_mapping

OUTPUT_NAME = "mapped_underlying_market_regime_evidence.json"
BENCHMARKS = ("SPY", "QQQ")
MIN_BARS = 50


def _load_closes(path: Path) -> list[float]:
    if not path.is_file():
        return []
    closes: list[float] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                close = float(row["close"])
            except (KeyError, TypeError, ValueError):
                return []
            if close <= 0:
                return []
            closes.append(close)
    return closes


def _benchmark_support(closes: list[float]) -> dict[str, Any] | None:
    if len(closes) < MIN_BARS:
        return None
    latest = closes[-1]
    sma20 = fmean(closes[-20:])
    sma50 = fmean(closes[-50:])
    ret20 = (latest / closes[-21] - 1.0) * 100.0
    score = 0.0
    if latest > sma20:
        score += 35.0
    if sma20 > sma50:
        score += 35.0
    if ret20 > 0:
        score += 30.0
    return {
        "score": round(score, 2),
        "latest_close": round(latest, 4),
        "sma_20": round(sma20, 4),
        "sma_50": round(sma50, 4),
        "return_20d_pct": round(ret20, 4),
        "bars_used": len(closes),
    }


def build_mapped_underlying_market_regime_evidence(
    *, registry_path: str | Path, data_dir: str | Path
) -> dict[str, Any]:
    mapping = preferred_vehicle_mapping(registry_path)
    root = Path(data_dir)
    benchmark_results: dict[str, Any] = {}
    missing: list[str] = []
    for symbol in BENCHMARKS:
        result = _benchmark_support(_load_closes(root / f"{symbol}.csv"))
        if result is None:
            missing.append(symbol)
        else:
            benchmark_results[symbol] = result

    regime_score: float | None = None
    if not missing:
        regime_score = round(fmean(result["score"] for result in benchmark_results.values()), 2)

    rows = [
        {
            "underlying_symbol": underlying,
            "preferred_vehicle": mapping[underlying],
            "market_regime_support_score": regime_score,
            "evidence_status": "AVAILABLE" if regime_score is not None else "MISSING_OR_INSUFFICIENT_BENCHMARK_HISTORY",
        }
        for underlying in sorted(mapping)
    ]
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "ai_cio_discovery_status_used_as_score": False,
        "mapped_underlying_count": len(mapping),
        "market_regime_support_score": regime_score,
        "benchmarks": benchmark_results,
        "missing_benchmarks": missing,
        "rows": rows,
    }


def write_mapped_underlying_market_regime_evidence(payload: Mapping[str, Any], *, output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / OUTPUT_NAME
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=root) as handle:
        json.dump(dict(payload), handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return path


def build_and_write_mapped_underlying_market_regime_evidence(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    data_dir: str | Path = "data",
    output_dir: str | Path = "results",
) -> dict[str, Any]:
    payload = build_mapped_underlying_market_regime_evidence(registry_path=registry_path, data_dir=data_dir)
    write_mapped_underlying_market_regime_evidence(payload, output_dir=output_dir)
    return payload


if __name__ == "__main__":
    report = build_and_write_mapped_underlying_market_regime_evidence()
    print(f"Mapped underlying market regime evidence: score={report['market_regime_support_score']}")

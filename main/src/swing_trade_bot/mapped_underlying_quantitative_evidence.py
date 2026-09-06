"""Swing-owned quantitative evidence for persistently mapped underlyings.

Calculates only Momentum and Technical Analysis evidence from normalized daily
OHLCV history. It does not infer fundamentals, news, conviction, regime, or
portfolio risk, and it never uses AI CIO discovery status as a score.
"""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping

from .leveraged_vehicle_registry import preferred_vehicle_mapping

OUTPUT_NAME = "mapped_underlying_quantitative_evidence.json"
MIN_BARS = 50


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _load_rows(path: Path) -> list[dict[str, float | str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, float | str]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                rows.append({
                    "date": str(row["date"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                })
            except (KeyError, TypeError, ValueError):
                return []
    return rows


def _rsi14(closes: list[float]) -> float | None:
    if len(closes) < 15:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(len(closes) - 14, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = fmean(gains)
    avg_loss = fmean(losses)
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def score_quantitative_evidence(rows: list[dict[str, float | str]]) -> dict[str, Any] | None:
    if len(rows) < MIN_BARS:
        return None
    closes = [float(row["close"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    if any(not math.isfinite(value) or value <= 0 for value in closes):
        return None
    latest = closes[-1]
    sma20 = fmean(closes[-20:])
    sma50 = fmean(closes[-50:])
    ret5 = (latest / closes[-6] - 1.0) * 100.0
    ret20 = (latest / closes[-21] - 1.0) * 100.0
    rsi = _rsi14(closes)
    recent_volume = fmean(volumes[-20:])
    prior_volume = fmean(volumes[-40:-20]) if len(volumes) >= 40 else recent_volume
    volume_ratio = recent_volume / prior_volume if prior_volume > 0 else 1.0

    momentum = 50.0
    momentum += max(-20.0, min(20.0, ret20 * 1.5))
    momentum += max(-10.0, min(10.0, ret5 * 2.0))
    momentum += max(-10.0, min(10.0, (volume_ratio - 1.0) * 25.0))

    technical = 50.0
    technical += 15.0 if latest > sma20 else -15.0
    technical += 15.0 if sma20 > sma50 else -15.0
    technical += 10.0 if latest > sma50 else -10.0
    if rsi is not None:
        if 50.0 <= rsi <= 70.0:
            technical += 10.0
        elif rsi < 40.0 or rsi > 80.0:
            technical -= 10.0

    return {
        "momentum_score": _clamp(momentum),
        "technical_analysis_score": _clamp(technical),
        "metrics": {
            "latest_close": round(latest, 4),
            "return_5d_pct": round(ret5, 4),
            "return_20d_pct": round(ret20, 4),
            "sma_20": round(sma20, 4),
            "sma_50": round(sma50, 4),
            "rsi_14": round(rsi, 4) if rsi is not None else None,
            "volume_20d_vs_prior_20d": round(volume_ratio, 4),
            "bars_used": len(rows),
        },
    }


def build_mapped_underlying_quantitative_evidence(*, registry_path: str | Path, data_dir: str | Path) -> dict[str, Any]:
    mapping = preferred_vehicle_mapping(registry_path)
    root = Path(data_dir)
    rows: list[dict[str, Any]] = []
    scored = 0
    for underlying in sorted(mapping):
        source = root / f"{underlying}.csv"
        result = score_quantitative_evidence(_load_rows(source))
        if result is None:
            rows.append({
                "underlying_symbol": underlying,
                "preferred_vehicle": mapping[underlying],
                "momentum_score": None,
                "technical_analysis_score": None,
                "evidence_status": "MISSING_OR_INSUFFICIENT_OHLCV",
                "source_path": str(source),
            })
            continue
        scored += 1
        rows.append({
            "underlying_symbol": underlying,
            "preferred_vehicle": mapping[underlying],
            **result,
            "evidence_status": "AVAILABLE",
            "source_path": str(source),
        })
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "ai_cio_discovery_status_used_as_score": False,
        "mapped_underlying_count": len(mapping),
        "quantitatively_scored_count": scored,
        "rows": rows,
    }


def write_mapped_underlying_quantitative_evidence(payload: Mapping[str, Any], *, output_dir: str | Path) -> Path:
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


def build_and_write_mapped_underlying_quantitative_evidence(*, registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json", data_dir: str | Path = "data", output_dir: str | Path = "results") -> dict[str, Any]:
    payload = build_mapped_underlying_quantitative_evidence(registry_path=registry_path, data_dir=data_dir)
    write_mapped_underlying_quantitative_evidence(payload, output_dir=output_dir)
    return payload


if __name__ == "__main__":
    report = build_and_write_mapped_underlying_quantitative_evidence()
    print(f"Mapped underlying quantitative evidence: {report['quantitatively_scored_count']}/{report['mapped_underlying_count']} scored")

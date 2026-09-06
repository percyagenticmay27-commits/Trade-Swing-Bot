"""Swing-owned fundamental evidence for persistently mapped underlyings.

The module scores underlying-company fundamentals only from explicit raw company
metrics. It does not use AI CIO discovery status, leveraged-vehicle performance,
or Entry Score as fundamental evidence.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .leveraged_vehicle_registry import preferred_vehicle_mapping

OUTPUT_NAME = "mapped_underlying_fundamental_evidence.json"
MIN_REQUIRED_METRICS = 4

METRIC_NAMES = (
    "revenue_growth_pct",
    "earnings_growth_pct",
    "operating_margin_pct",
    "free_cash_flow_margin_pct",
    "return_on_equity_pct",
    "current_ratio",
    "debt_to_equity",
)


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _positive_growth_score(value: float) -> float:
    return _clamp(50.0 + value * 1.5)


def _margin_score(value: float) -> float:
    return _clamp(40.0 + value * 2.0)


def _roe_score(value: float) -> float:
    return _clamp(40.0 + value * 1.5)


def _current_ratio_score(value: float) -> float:
    if value <= 0:
        return 0.0
    if value < 1.0:
        return _clamp(value * 40.0)
    if value <= 2.5:
        return _clamp(60.0 + (value - 1.0) * 20.0)
    return 90.0


def _debt_to_equity_score(value: float) -> float:
    if value < 0:
        return 50.0
    if value <= 0.5:
        return 95.0
    if value <= 1.0:
        return 80.0
    if value <= 2.0:
        return 60.0
    if value <= 3.0:
        return 40.0
    return 20.0


def score_fundamental_metrics(metrics: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a transparent 0-100 fundamental score from available raw metrics."""
    values: dict[str, float] = {}
    for name in METRIC_NAMES:
        raw = metrics.get(name)
        if raw in (None, ""):
            continue
        try:
            values[name] = float(raw)
        except (TypeError, ValueError):
            continue
    if len(values) < MIN_REQUIRED_METRICS:
        return None

    components: dict[str, float] = {}
    if "revenue_growth_pct" in values:
        components["revenue_growth"] = _positive_growth_score(values["revenue_growth_pct"])
    if "earnings_growth_pct" in values:
        components["earnings_growth"] = _positive_growth_score(values["earnings_growth_pct"])
    if "operating_margin_pct" in values:
        components["operating_margin"] = _margin_score(values["operating_margin_pct"])
    if "free_cash_flow_margin_pct" in values:
        components["free_cash_flow_margin"] = _margin_score(values["free_cash_flow_margin_pct"])
    if "return_on_equity_pct" in values:
        components["return_on_equity"] = _roe_score(values["return_on_equity_pct"])
    if "current_ratio" in values:
        components["liquidity"] = _current_ratio_score(values["current_ratio"])
    if "debt_to_equity" in values:
        components["leverage"] = _debt_to_equity_score(values["debt_to_equity"])

    score = sum(components.values()) / len(components)
    return {
        "fundamental_analysis_score": _clamp(score),
        "metric_count": len(values),
        "metrics": values,
        "score_breakdown": components,
    }


def build_mapped_underlying_fundamental_evidence(
    *,
    registry_path: str | Path,
    metric_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    mapping = preferred_vehicle_mapping(registry_path)
    by_symbol = {
        str(row.get("underlying_symbol", row.get("symbol", ""))).strip().upper(): row
        for row in metric_rows
        if str(row.get("underlying_symbol", row.get("symbol", ""))).strip()
    }
    rows: list[dict[str, Any]] = []
    scored = 0
    for underlying in sorted(mapping):
        metrics = by_symbol.get(underlying)
        result = score_fundamental_metrics(metrics or {})
        if result is None:
            rows.append({
                "underlying_symbol": underlying,
                "preferred_vehicle": mapping[underlying],
                "fundamental_analysis_score": None,
                "evidence_status": "MISSING_OR_INSUFFICIENT_FUNDAMENTALS",
                "minimum_required_metrics": MIN_REQUIRED_METRICS,
            })
            continue
        scored += 1
        rows.append({
            "underlying_symbol": underlying,
            "preferred_vehicle": mapping[underlying],
            **result,
            "evidence_status": "AVAILABLE",
        })
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "ai_cio_discovery_status_used_as_score": False,
        "entry_score_used_as_fundamental_evidence": False,
        "mapped_underlying_count": len(mapping),
        "fundamentally_scored_count": scored,
        "rows": rows,
    }


def write_mapped_underlying_fundamental_evidence(payload: Mapping[str, Any], *, output_dir: str | Path) -> Path:
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

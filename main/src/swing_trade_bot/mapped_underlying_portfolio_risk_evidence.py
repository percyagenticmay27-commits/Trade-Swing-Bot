"""Swing-owned Portfolio Risk Adjustment evidence for mapped underlyings.

The score is supportive when adding a mapped vehicle would not duplicate an
existing paper position and the current paper portfolio is not overly
concentrated. Missing portfolio evidence fails closed instead of assuming low
risk. This module never places orders or moves capital.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .leveraged_vehicle_registry import preferred_vehicle_mapping

OUTPUT_NAME = "mapped_underlying_portfolio_risk_evidence.json"
DEFAULT_POSITIONS_FILE = "paper_portfolio_positions.json"


def _load_positions(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("positions") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return None
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _allocation_percent(row: Mapping[str, Any]) -> float:
    try:
        value = float(row.get("allocation_percent", 0.0))
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) and value >= 0 else 0.0


def score_candidate_portfolio_risk(
    *, preferred_vehicle: str, positions: list[Mapping[str, Any]]
) -> dict[str, Any]:
    held_symbols = {str(row.get("symbol", "")).strip().upper() for row in positions}
    allocations = [_allocation_percent(row) for row in positions]
    max_allocation = max(allocations, default=0.0)
    concentration_index = sum((value / 100.0) ** 2 for value in allocations)

    score = 100.0
    duplicate_position = preferred_vehicle.upper() in held_symbols
    if duplicate_position:
        score -= 40.0
    if max_allocation > 40.0:
        score -= 20.0
    elif max_allocation > 30.0:
        score -= 10.0
    if concentration_index > 0.30:
        score -= 20.0
    elif concentration_index > 0.20:
        score -= 10.0

    return {
        "portfolio_risk_adjustment_score": round(max(0.0, min(100.0, score)), 2),
        "duplicate_position": duplicate_position,
        "current_position_count": len(positions),
        "max_existing_allocation_percent": round(max_allocation, 4),
        "portfolio_concentration_index": round(concentration_index, 6),
    }


def build_mapped_underlying_portfolio_risk_evidence(
    *,
    registry_path: str | Path,
    results_dir: str | Path,
    positions_path: str | Path | None = None,
) -> dict[str, Any]:
    mapping = preferred_vehicle_mapping(registry_path)
    source = Path(positions_path) if positions_path is not None else Path(results_dir) / "paper_ledger" / DEFAULT_POSITIONS_FILE
    positions = _load_positions(source)
    rows: list[dict[str, Any]] = []
    scored = 0
    for underlying in sorted(mapping):
        if positions is None:
            rows.append({
                "underlying_symbol": underlying,
                "preferred_vehicle": mapping[underlying],
                "portfolio_risk_adjustment_score": None,
                "evidence_status": "MISSING_PAPER_PORTFOLIO_EVIDENCE",
                "source_path": str(source),
            })
            continue
        scored += 1
        rows.append({
            "underlying_symbol": underlying,
            "preferred_vehicle": mapping[underlying],
            **score_candidate_portfolio_risk(preferred_vehicle=mapping[underlying], positions=positions),
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
        "capital_movement_enabled": False,
        "mapped_underlying_count": len(mapping),
        "portfolio_risk_scored_count": scored,
        "rows": rows,
    }


def write_mapped_underlying_portfolio_risk_evidence(payload: Mapping[str, Any], *, output_dir: str | Path) -> Path:
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


def build_and_write_mapped_underlying_portfolio_risk_evidence(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    results_dir: str | Path = "results",
    positions_path: str | Path | None = None,
) -> dict[str, Any]:
    payload = build_mapped_underlying_portfolio_risk_evidence(
        registry_path=registry_path,
        results_dir=results_dir,
        positions_path=positions_path,
    )
    write_mapped_underlying_portfolio_risk_evidence(payload, output_dir=results_dir)
    return payload


if __name__ == "__main__":
    report = build_and_write_mapped_underlying_portfolio_risk_evidence()
    print(f"Mapped underlying portfolio risk evidence: {report['portfolio_risk_scored_count']}/{report['mapped_underlying_count']} scored")

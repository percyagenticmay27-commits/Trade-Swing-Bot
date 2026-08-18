"""Swing-owned evidence refresh for the persistent mapped-underlying universe.

This orchestration layer intentionally does not score opportunities and does not
consume AI CIO discovery status as strategy evidence.  It snapshots the latest
Swing-owned component evidence for every persistently mapped underlying so the
frozen Opportunity Quality Version 1.2 engine can rank the universe afterward.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .leveraged_vehicle_registry import preferred_vehicle_mapping
from .opportunity_quality_engine import COMPONENT_WEIGHTS
from .opportunity_quality_runtime_report import collect_runtime_evidence

STRATEGY_ID = "SWING-001"
SCHEMA_VERSION = "1.0"
OUTPUT_NAME = "mapped_universe_evidence_refresh.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_mapped_universe_evidence_refresh(
    *,
    registry_path: str | Path,
    results_dir: str | Path,
    source_paths: Sequence[Path] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Snapshot available Swing-owned OQ component evidence for mapped names."""
    mapping = preferred_vehicle_mapping(registry_path)
    evidence = collect_runtime_evidence(results_dir=Path(results_dir), source_paths=source_paths)

    rows: list[dict[str, Any]] = []
    complete = 0
    with_evidence = 0
    for underlying in sorted(mapping):
        source: Mapping[str, Any] = evidence.get(underlying, {})
        components = {
            component: source.get(component)
            for component in COMPONENT_WEIGHTS
        }
        present = [name for name, value in components.items() if value is not None]
        missing = [name for name, value in components.items() if value is None]
        if present:
            with_evidence += 1
        if not missing:
            complete += 1
        rows.append(
            {
                "underlying_symbol": underlying,
                "preferred_vehicle": mapping[underlying],
                "component_scores": components,
                "component_evidence_count": len(present),
                "component_evidence_complete": not missing,
                "missing_components": missing,
                "evidence_sources": list(source.get("sources", [])),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "universe_authority": "SWING_PERSISTENT_VERIFIED_MAPPING_REGISTRY",
        "evidence_authority": "SWING_OWNED_RUNTIME_EVIDENCE",
        "ai_cio_discovery_status_used_as_score": False,
        "entry_score_used_as_opportunity_quality_component": False,
        "mapped_underlying_count": len(mapping),
        "underlyings_with_component_evidence": with_evidence,
        "underlyings_with_complete_component_evidence": complete,
        "rows": rows,
    }


def write_mapped_universe_evidence_refresh(
    payload: Mapping[str, Any], *, output_dir: str | Path
) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / OUTPUT_NAME
    _atomic_write_text(path, json.dumps(dict(payload), indent=2) + "\n")
    return path


def build_and_write_mapped_universe_evidence_refresh(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    results_dir: str | Path = "results",
    source_paths: Sequence[Path] | None = None,
) -> dict[str, Any]:
    payload = build_mapped_universe_evidence_refresh(
        registry_path=registry_path,
        results_dir=results_dir,
        source_paths=source_paths,
    )
    write_mapped_universe_evidence_refresh(payload, output_dir=results_dir)
    return payload


def _atomic_write_text(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


if __name__ == "__main__":
    report = build_and_write_mapped_universe_evidence_refresh()
    print(
        "Mapped universe evidence refresh: "
        f"{report['mapped_underlying_count']} mapped; "
        f"{report['underlyings_with_component_evidence']} with evidence; "
        f"{report['underlyings_with_complete_component_evidence']} complete"
    )

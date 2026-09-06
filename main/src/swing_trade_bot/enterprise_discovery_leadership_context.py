"""Read-only preservation of AI CIO Discovery Leadership v1 evidence.

AI CIO discovers leadership. SWING-001 evaluates the trade.

This module preserves optional additive Discovery Leadership fields from the
SWING-001 schema-1.0 enterprise discovery bucket without recalculating,
normalizing, scoring, or promoting them into Swing-owned lifecycle or execution
state. The resulting artifact is context only for downstream Swing analysis.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .enterprise_discovery_bucket import discover_bucket_path, load_discovery_bucket

STRATEGY_ID = "SWING-001"
SCHEMA_VERSION = "1.0"
OUTPUT_NAME = "enterprise_discovery_leadership_context.json"

LEADERSHIP_FIELDS = (
    "discovery_leadership_score",
    "discovery_leadership_classification",
    "relative_leadership",
    "sector_leadership",
    "industry_leadership",
    "theme_leadership",
    "discovery_reasons",
    "discovery_warnings",
)


def _candidate_context(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return upstream leadership evidence unchanged except for symbol casing."""
    row: dict[str, Any] = {
        "underlying_symbol": str(candidate.get("underlying_symbol", "")).strip().upper(),
        "discovery_status": str(candidate.get("discovery_status", "")).strip().upper(),
    }
    for field in LEADERSHIP_FIELDS:
        if field in candidate:
            row[field] = copy.deepcopy(candidate[field])
    return row


def build_discovery_leadership_context(bucket: Mapping[str, Any]) -> dict[str, Any]:
    """Build a context-only view without deriving any Swing strategy signal."""
    candidates = [
        _candidate_context(item)
        for item in bucket.get("candidates", [])
        if isinstance(item, Mapping)
    ]
    enriched = sum(
        any(field in row for field in LEADERSHIP_FIELDS)
        for row in candidates
    )
    warning_count = sum(
        len(row.get("discovery_warnings", []))
        for row in candidates
        if isinstance(row.get("discovery_warnings", []), list)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "ownership_statement": "AI CIO discovers leadership. SWING-001 evaluates the trade.",
        "leadership_owner": "AI_CIO",
        "leadership_recalculated_by_swing": False,
        "leadership_used_as_automatic_buy_signal": False,
        "opportunity_quality_weights_changed": False,
        "entry_score_changed": False,
        "source_bucket_schema_version": str(bucket.get("schema_version", "")),
        "source_bucket_strategy_id": str(bucket.get("strategy_id", STRATEGY_ID)),
        "source_bucket_generated_at": bucket.get("generated_at_utc") or bucket.get("generated_at"),
        "candidate_count": len(candidates),
        "leadership_enriched_candidate_count": enriched,
        "discovery_warning_count": warning_count,
        "candidates": candidates,
    }


def write_discovery_leadership_context(
    payload: Mapping[str, Any], *, output_dir: str | Path = "results"
) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / OUTPUT_NAME
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=root) as handle:
        json.dump(dict(payload), handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, destination)
    return destination


def refresh_enterprise_discovery_leadership_context(
    *,
    swing_root: str | Path | None = None,
    ai_cio_repository: str | Path | None = None,
) -> dict[str, Any]:
    """Read the validated AI CIO bucket and publish optional leadership context."""
    root = Path(swing_root) if swing_root is not None else Path.cwd()
    bucket_path = discover_bucket_path(repository_root=ai_cio_repository)
    if not bucket_path.is_file():
        payload = build_discovery_leadership_context(
            {"schema_version": SCHEMA_VERSION, "strategy_id": STRATEGY_ID, "candidates": []}
        )
        payload["source_bucket_available"] = False
    else:
        bucket = load_discovery_bucket(bucket_path)
        payload = build_discovery_leadership_context(bucket)
        payload["source_bucket_available"] = True
    payload["source_bucket_path"] = str(bucket_path)
    write_discovery_leadership_context(payload, output_dir=root / "results")
    return payload


if __name__ == "__main__":
    report = refresh_enterprise_discovery_leadership_context()
    print(
        "Enterprise Discovery Leadership context: "
        f"{report['leadership_enriched_candidate_count']}/{report['candidate_count']} enriched"
    )

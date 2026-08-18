"""Weekly Swing-owned review of the persistent mapped-underlying universe.

AI CIO discovers broad-market opportunities, but Swing owns strategy suitability.
This module never uses AI CIO discovery status as a Swing score. It reads the
persistent leveraged-vehicle registry, assembles Swing-owned component evidence,
invokes the frozen Opportunity Quality engine, and ranks mapped underlyings for
watchlist attention. Entry Score remains display-only and is never used to rank or
select the weekly watchlist universe.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .leveraged_vehicle_registry import preferred_vehicle_mapping
from .opportunity_quality_engine import COMPONENT_WEIGHTS, OpportunityQualityEngine
from .opportunity_quality_runtime_report import build_inputs_from_evidence, collect_runtime_evidence

STRATEGY_ID = "SWING-001"
SCHEMA_VERSION = "1.0"
DEFAULT_MAX_WATCHLIST_SIZE = 15
MIN_OPPORTUNITY_QUALITY_SCORE = 70.0


@dataclass(frozen=True, slots=True)
class WeeklyMappedUniverseRow:
    rank: int
    underlying_symbol: str
    preferred_vehicle: str
    opportunity_quality_score: float
    opportunity_quality_level: str
    selected_for_watchlist: bool
    entry_score: float
    entry_score_display_only: bool
    component_evidence_count: int
    component_evidence_complete: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_weekly_mapped_universe_review(
    *,
    registry_path: str | Path,
    results_dir: str | Path,
    max_watchlist_size: int = DEFAULT_MAX_WATCHLIST_SIZE,
    minimum_quality_score: float = MIN_OPPORTUNITY_QUALITY_SCORE,
    source_paths: Sequence[Path] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Rank all persistently mapped underlyings using Swing-owned evidence only."""
    if max_watchlist_size <= 0:
        raise ValueError("max_watchlist_size must be positive")
    if not 0.0 <= minimum_quality_score <= 100.0:
        raise ValueError("minimum_quality_score must be between 0 and 100")

    mapping = preferred_vehicle_mapping(registry_path)
    evidence = collect_runtime_evidence(results_dir=Path(results_dir), source_paths=source_paths)

    mapped_evidence: dict[str, Mapping[str, Any]] = {
        symbol: evidence.get(symbol, {"symbol": symbol, "sources": []})
        for symbol in sorted(mapping)
    }
    inputs = build_inputs_from_evidence(mapped_evidence)
    report = OpportunityQualityEngine(paper_trade_mode=True, system_mode="LIVE").evaluate(inputs)

    scored = []
    for row in report.rows:
        source = mapped_evidence[row.symbol]
        component_count = sum(
            1
            for component in COMPONENT_WEIGHTS
            if source.get(component) is not None
        )
        scored.append((row, component_count))

    scored.sort(key=lambda item: (-item[0].opportunity_quality_score, item[0].symbol))
    eligible_symbols = [
        row.symbol
        for row, component_count in scored
        if row.opportunity_quality_score >= minimum_quality_score and component_count > 0
    ][:max_watchlist_size]
    selected = set(eligible_symbols)

    rows: list[WeeklyMappedUniverseRow] = []
    for rank, (row, component_count) in enumerate(scored, start=1):
        rows.append(
            WeeklyMappedUniverseRow(
                rank=rank,
                underlying_symbol=row.symbol,
                preferred_vehicle=mapping[row.symbol],
                opportunity_quality_score=row.opportunity_quality_score,
                opportunity_quality_level=row.opportunity_quality_level,
                selected_for_watchlist=row.symbol in selected,
                entry_score=row.entry_score,
                entry_score_display_only=True,
                component_evidence_count=component_count,
                component_evidence_complete=component_count == len(COMPONENT_WEIGHTS),
            )
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
        "ranking_authority": "FROZEN_OPPORTUNITY_QUALITY_ENGINE_V1_2",
        "ai_cio_discovery_status_used_in_ranking": False,
        "entry_score_display_only": True,
        "entry_score_used_in_ranking": False,
        "entry_score_used_for_watchlist_selection": False,
        "minimum_opportunity_quality_score": minimum_quality_score,
        "max_watchlist_size": max_watchlist_size,
        "mapped_underlying_count": len(mapping),
        "selected_watchlist_count": len(selected),
        "selected_underlyings": eligible_symbols,
        "rows": [asdict(row) for row in rows],
    }


def write_weekly_mapped_universe_review(
    payload: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, Path]:
    """Atomically publish JSON/CSV/Markdown views of the weekly review."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "weekly_mapped_universe_review.json"
    csv_path = root / "weekly_mapped_universe_review.csv"
    md_path = root / "weekly_mapped_universe_review.md"

    _atomic_write_text(json_path, json.dumps(dict(payload), indent=2) + "\n")

    rows = list(payload.get("rows", []))
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False, dir=root) as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, csv_path)

    lines = [
        "# Weekly Mapped Universe Review",
        "",
        "Paper-only: true",
        "AI CIO discovers; Swing independently ranks persistent mapped underlyings.",
        "Entry Score is display-only and is not used for weekly ranking or watchlist selection.",
        "",
        "| Rank | Underlying | Vehicle | Opportunity Quality | Level | Watchlist | Evidence |",
        "|---:|---|---|---:|---|---|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['rank']} | {row['underlying_symbol']} | {row['preferred_vehicle']} | "
            f"{float(row['opportunity_quality_score']):.2f} | {row['opportunity_quality_level']} | "
            f"{'YES' if row['selected_for_watchlist'] else 'NO'} | {row['component_evidence_count']}/7 |"
        )
    _atomic_write_text(md_path, "\n".join(lines) + "\n")
    return json_path, csv_path, md_path


def build_and_write_weekly_mapped_universe_review(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    results_dir: str | Path = "results",
    max_watchlist_size: int = DEFAULT_MAX_WATCHLIST_SIZE,
) -> dict[str, Any]:
    payload = build_weekly_mapped_universe_review(
        registry_path=registry_path,
        results_dir=results_dir,
        max_watchlist_size=max_watchlist_size,
    )
    write_weekly_mapped_universe_review(payload, output_dir=results_dir)
    return payload


def _atomic_write_text(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


if __name__ == "__main__":
    report = build_and_write_weekly_mapped_universe_review()
    print(
        "Weekly mapped universe review: "
        f"{report['mapped_underlying_count']} mapped; "
        f"{report['selected_watchlist_count']} selected"
    )

"""Current-cycle committee gate evidence refresh for the paper-only Swing Bot.

This module wires the already-governed Entry Score V1.0 and Thesis Monitor V2
producers into the Opportunity Quality input/report dependency chain. It does not
change Entry Score semantics, Thesis V2 weights, Opportunity Quality weights,
committee thresholds, allocation policy, or execution behavior.

Dependency order:

    current watchlist (produced by caller)
      -> fresh Daily Entry Score evidence
      -> bootstrap Opportunity Quality inputs/report
      -> dynamic Thesis Monitor V2
      -> final Opportunity Quality inputs/report with thesis_intact

The final artifacts are then safe for the existing committee/allocation pipeline
to consume. All operations are paper-only and advisory-only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .entry_score_evidence_refresh import refresh_entry_score_evidence
from .opportunity_quality_engine import build_opportunity_quality_report
from .opportunity_quality_inputs import build_and_write_opportunity_quality_inputs
from .thesis_monitor_v2 import build_and_write_thesis_monitor_v2

MODULE_VERSION = "1.0.0"
STRATEGY_ID = "SWING-001"


def refresh_daily_committee_evidence(
    *,
    project_root: str | Path,
    results_dir: str | Path,
    quality_input_path: str | Path,
    assignments_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    paper_trade_mode: bool = True,
) -> dict[str, Any]:
    """Refresh Entry, Thesis V2, and final OQ committee evidence in order."""
    if not paper_trade_mode:
        raise ValueError("daily committee evidence refresh requires paper_trade_mode=True")

    root = Path(project_root).resolve()
    results = Path(results_dir)
    if not results.is_absolute():
        results = root / results
    quality_inputs = Path(quality_input_path)
    if not quality_inputs.is_absolute():
        quality_inputs = root / quality_inputs
    assignments = Path(assignments_path) if assignments_path is not None else root / "configs" / "frozen_strategy_assignments.json"
    daily_data = Path(data_dir) if data_dir is not None else root / "data"
    if not daily_data.is_absolute():
        daily_data = root / daily_data

    watchlist_path = results / "watchlist_report.json"
    if not watchlist_path.is_file():
        raise FileNotFoundError(f"Current watchlist must exist before committee evidence refresh: {watchlist_path}")

    entry_summary = refresh_entry_score_evidence(
        project_root=root,
        results_dir=results,
        data_dir=daily_data,
    )

    # Bootstrap OQ from current evidence + fresh Entry Score. Thesis V2 consumes
    # these OQ components and score, but thesis health does not alter OQ itself.
    build_and_write_opportunity_quality_inputs(results, quality_inputs)
    build_opportunity_quality_report(
        input_path=quality_inputs,
        output_dir=results,
        paper_trade_mode=True,
    )

    thesis_payload = build_and_write_thesis_monitor_v2(
        results_dir=results,
        assignments_path=assignments,
    )

    # Rebuild once so the final committee-facing OQ inputs include the newly
    # generated thesis_intact value. Recomputing OQ is deterministic because
    # thesis_intact is not an Opportunity Quality component.
    build_and_write_opportunity_quality_inputs(results, quality_inputs)
    build_opportunity_quality_report(
        input_path=quality_inputs,
        output_dir=results,
        paper_trade_mode=True,
    )

    reviews = thesis_payload.get("reviews", [])
    return {
        "module_version": MODULE_VERSION,
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "allocation_bypass_allowed": False,
        "entry_score_policy_changed": False,
        "thesis_policy_changed": False,
        "opportunity_quality_policy_changed": False,
        "entry_score_summary": entry_summary,
        "thesis_review_count": len(reviews) if isinstance(reviews, list) else 0,
        "thesis_intact_symbols": [
            str(row.get("underlying_symbol", "")).strip().upper()
            for row in reviews
            if isinstance(row, dict) and row.get("thesis_intact") is True
        ] if isinstance(reviews, list) else [],
        "artifacts": [
            str(results / "entry_score_market_data_refresh.json"),
            str(results / "entry_score_report.json"),
            str(results / "entry_score_report.csv"),
            str(results / "thesis_monitor_v2_report.json"),
            str(results / "thesis_monitor_v2_report.md"),
            str(quality_inputs),
            str(results / "opportunity_quality_report.csv"),
            str(results / "opportunity_quality_report.json"),
            str(results / "opportunity_quality_report.md"),
        ],
    }

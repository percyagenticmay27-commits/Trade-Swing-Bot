"""Tuesday mapped-universe workflow for SWING-001.

Sequence:
1. Snapshot Swing-owned mapped-universe component evidence.
2. Run the frozen Opportunity Quality V1.2 mapped-universe review.

This workflow is paper-only. It does not place orders, execute trades, or use AI CIO
discovery status or Entry Score as Opportunity Quality inputs.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mapped_universe_evidence_refresh import build_and_write_mapped_universe_evidence_refresh
from .weekly_mapped_universe_review import build_and_write_weekly_mapped_universe_review

STRATEGY_ID = "SWING-001"
SCHEMA_VERSION = "1.0"
STATUS_FILENAME = "tuesday_mapped_universe_workflow_status.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_tuesday_mapped_universe_workflow(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    results_dir: str | Path = "results",
    max_watchlist_size: int = 15,
) -> dict[str, Any]:
    """Run evidence snapshot then mapped-universe ranking, failing closed on errors."""
    generated_at = _utc_now()
    status: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "generated_at_utc": generated_at,
        "workflow": "SWING_MAPPED_UNIVERSE_TUESDAY_REVIEW",
        "steps": [],
        "status": "STARTED",
    }

    try:
        evidence = build_and_write_mapped_universe_evidence_refresh(
            registry_path=registry_path,
            results_dir=results_dir,
        )
        status["steps"].append(
            {
                "name": "MAPPED_UNIVERSE_EVIDENCE_REFRESH",
                "status": "PASSED",
                "mapped_underlying_count": evidence["mapped_underlying_count"],
                "underlyings_with_component_evidence": evidence["underlyings_with_component_evidence"],
                "underlyings_with_complete_component_evidence": evidence["underlyings_with_complete_component_evidence"],
            }
        )

        review = build_and_write_weekly_mapped_universe_review(
            registry_path=registry_path,
            results_dir=results_dir,
            max_watchlist_size=max_watchlist_size,
        )
        status["steps"].append(
            {
                "name": "FROZEN_OPPORTUNITY_QUALITY_V1_2_RANKING",
                "status": "PASSED",
                "mapped_underlying_count": review["mapped_underlying_count"],
                "selected_watchlist_count": review["selected_watchlist_count"],
                "selected_underlyings": review["selected_underlyings"],
            }
        )
        status["status"] = "COMPLETE"
        status["selected_watchlist_count"] = review["selected_watchlist_count"]
        status["selected_underlyings"] = review["selected_underlyings"]
    except Exception as exc:
        status["status"] = "FAILED"
        status["error"] = f"{type(exc).__name__}: {exc}"
        _write_status(status, results_dir)
        raise

    _write_status(status, results_dir)
    return status


def _write_status(payload: dict[str, Any], results_dir: str | Path) -> Path:
    root = Path(results_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / STATUS_FILENAME
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=root) as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return path


if __name__ == "__main__":
    result = run_tuesday_mapped_universe_workflow()
    print(
        "Tuesday mapped universe workflow: "
        f"{result['status']}; {result.get('selected_watchlist_count', 0)} selected"
    )

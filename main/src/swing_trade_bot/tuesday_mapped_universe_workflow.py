"""Tuesday mapped-universe workflow for SWING-001.

Sequence:
1. Refresh mapped-underlying daily OHLCV using the existing read-only market-data chain.
2. Generate Swing-owned Momentum and Technical Analysis evidence.
3. Refresh raw underlying-company fundamentals from SEC EDGAR companyfacts.
4. Generate Swing-owned Fundamental Analysis evidence.
5. Generate Swing-owned Market Intelligence and Conviction evidence from dated trusted mentions.
6. Snapshot all available Swing-owned Opportunity Quality component evidence.
7. Run the frozen Opportunity Quality V1.2 mapped-universe review.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mapped_underlying_fundamental_data_refresh import build_and_write_mapped_underlying_fundamental_data
from .mapped_underlying_fundamental_evidence import (
    build_mapped_underlying_fundamental_evidence,
    write_mapped_underlying_fundamental_evidence,
)
from .mapped_underlying_intelligence_evidence import build_and_write_mapped_underlying_intelligence_evidence
from .mapped_underlying_market_data_refresh import refresh_and_write_mapped_underlying_market_data
from .mapped_underlying_quantitative_evidence import build_and_write_mapped_underlying_quantitative_evidence
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
    data_dir: str | Path = "data",
    max_watchlist_size: int = 15,
) -> dict[str, Any]:
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
        market = refresh_and_write_mapped_underlying_market_data(
            registry_path=registry_path,
            data_dir=data_dir,
            output_dir=results_dir,
            refresh=True,
        )
        status["steps"].append({
            "name": "MAPPED_UNDERLYING_MARKET_DATA_REFRESH",
            "status": "PASSED",
            "mapped_underlying_count": market["mapped_underlying_count"],
            "current_market_data_count": market["current_market_data_count"],
        })

        quantitative = build_and_write_mapped_underlying_quantitative_evidence(
            registry_path=registry_path, data_dir=data_dir, output_dir=results_dir
        )
        status["steps"].append({
            "name": "MOMENTUM_AND_TECHNICAL_EVIDENCE",
            "status": "PASSED",
            "mapped_underlying_count": quantitative["mapped_underlying_count"],
            "quantitatively_scored_count": quantitative["quantitatively_scored_count"],
        })

        fundamental_data = build_and_write_mapped_underlying_fundamental_data(
            registry_path=registry_path,
            output_dir=results_dir,
        )
        status["steps"].append({
            "name": "SEC_FUNDAMENTAL_DATA_REFRESH",
            "status": "PASSED",
            "mapped_underlying_count": fundamental_data["mapped_underlying_count"],
            "underlyings_with_fundamental_metrics": fundamental_data["underlyings_with_fundamental_metrics"],
        })

        metric_rows = [
            {"underlying_symbol": row.get("underlying_symbol"), **dict(row.get("metrics", {}))}
            for row in fundamental_data.get("rows", [])
        ]
        fundamental = build_mapped_underlying_fundamental_evidence(
            registry_path=registry_path,
            metric_rows=metric_rows,
        )
        write_mapped_underlying_fundamental_evidence(fundamental, output_dir=results_dir)
        status["steps"].append({
            "name": "FUNDAMENTAL_ANALYSIS_EVIDENCE",
            "status": "PASSED",
            "mapped_underlying_count": fundamental["mapped_underlying_count"],
            "fundamentally_scored_count": fundamental["fundamentally_scored_count"],
        })

        intelligence = build_and_write_mapped_underlying_intelligence_evidence(
            registry_path=registry_path,
            mentions_path=Path(results_dir) / "discovery_mentions_runtime.csv",
            output_dir=results_dir,
        )
        status["steps"].append({
            "name": "MARKET_INTELLIGENCE_AND_CONVICTION_EVIDENCE",
            "status": "PASSED",
            "mapped_underlying_count": intelligence["mapped_underlying_count"],
            "underlyings_with_market_intelligence": intelligence["underlyings_with_market_intelligence"],
            "underlyings_with_conviction": intelligence["underlyings_with_conviction"],
        })

        evidence = build_and_write_mapped_universe_evidence_refresh(
            registry_path=registry_path, results_dir=results_dir
        )
        status["steps"].append({
            "name": "MAPPED_UNIVERSE_EVIDENCE_REFRESH",
            "status": "PASSED",
            "mapped_underlying_count": evidence["mapped_underlying_count"],
            "underlyings_with_component_evidence": evidence["underlyings_with_component_evidence"],
            "underlyings_with_complete_component_evidence": evidence["underlyings_with_complete_component_evidence"],
        })

        review = build_and_write_weekly_mapped_universe_review(
            registry_path=registry_path,
            results_dir=results_dir,
            max_watchlist_size=max_watchlist_size,
        )
        status["steps"].append({
            "name": "FROZEN_OPPORTUNITY_QUALITY_V1_2_RANKING",
            "status": "PASSED",
            "mapped_underlying_count": review["mapped_underlying_count"],
            "selected_watchlist_count": review["selected_watchlist_count"],
            "selected_underlyings": review["selected_underlyings"],
        })
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
    print(f"Tuesday mapped universe workflow: {result['status']}; {result.get('selected_watchlist_count', 0)} selected")

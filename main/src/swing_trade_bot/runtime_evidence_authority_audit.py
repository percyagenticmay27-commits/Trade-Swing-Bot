"""Audit Swing runtime KPI authority without changing calculations or host state.

This module is read-only. It verifies that Enterprise KPI values are traceable to
current Swing-owned artifacts and that paper-only safety boundaries remain intact.
It never imports or writes Trade-Dividend-Bot code and never places orders.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

STRATEGY_ID = "SWING-001"
PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _opportunity_score(payload: Mapping[str, Any] | None) -> float | None:
    if not payload:
        return None
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return None
    values: list[float] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        value = row.get("opportunity_quality_score")
        if isinstance(value, (int, float)):
            values.append(float(value))
    return max(values) if values else None


def _committee_value(payload: Mapping[str, Any] | None, committee_id: str, key: str) -> Any:
    steps = payload.get("committee_steps") if payload else None
    if not isinstance(steps, list):
        return None
    for step in steps:
        if not isinstance(step, Mapping) or step.get("committee_id") != committee_id:
            continue
        evidence = step.get("evidence")
        return evidence.get(key) if isinstance(evidence, Mapping) else None
    return None


def _count_rows(payload: Mapping[str, Any] | None, key: str) -> int | None:
    rows = payload.get(key) if payload else None
    return len(rows) if isinstance(rows, list) else None


def build_runtime_evidence_authority_audit(results_dir: str | Path = "results") -> dict[str, Any]:
    root = Path(results_dir)
    kpi = _load(root / "enterprise_strategy_kpis.json")
    opportunity = _load(root / "opportunity_quality_report.json")
    watchlist = _load(root / "watchlist_report.json")
    committee = _load(root / "swing_committee_runtime_evidence.json")
    portfolio = _load(root / "paper_ledger" / "paper_portfolio_summary.json")
    positions = _load(root / "paper_ledger" / "paper_portfolio_positions.json")
    performance = _load(root / "paper_ledger" / "paper_performance.json")
    market = _load(root / "market_data_refresh_status.json")

    errors: list[str] = []
    warnings: list[str] = []
    if not kpi:
        errors.append("enterprise_strategy_kpis.json is missing")
        kpi = {}
    if kpi.get("strategy_id") != STRATEGY_ID:
        errors.append("Enterprise KPI strategy_id is not SWING-001")

    safety = {
        "paper_trade_mode": kpi.get("paper_trade_mode"),
        "live_trading_enabled": kpi.get("live_trading_enabled"),
        "broker_execution_enabled": kpi.get("broker_execution_enabled"),
        "order_placement_enabled": kpi.get("order_placement_enabled"),
        "capital_movement_enabled": kpi.get("capital_movement_enabled"),
    }
    expected_safety = {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
    }
    for key, expected in expected_safety.items():
        if safety.get(key) is not expected:
            errors.append(f"Unsafe or missing Enterprise KPI safety flag: {key}")

    oq = _opportunity_score(opportunity)
    enterprise_oq = kpi.get("opportunity_quality")
    if oq is not None and enterprise_oq != oq:
        errors.append("Enterprise Opportunity Quality does not match opportunity_quality_report.json")

    committee_oq = _committee_value(committee, "OPPORTUNITY_COMMITTEE", "opportunity_quality_score")
    if oq is not None and committee_oq != oq:
        errors.append("Opportunity Committee does not consume current Opportunity Quality")

    entry_score = _committee_value(committee, "ENTRY_COMMITTEE", "entry_score")

    authoritative_win_rate = performance.get("win_rate_percent") if performance else None
    closed_trade_count = performance.get("closed_trade_count") if performance else None
    enterprise_win_rate = kpi.get("win_rate_percent")
    if not closed_trade_count:
        authoritative_win_rate = None
        if enterprise_win_rate is not None:
            errors.append("Enterprise win rate is populated without completed paper trades")
    elif enterprise_win_rate != authoritative_win_rate:
        errors.append("Enterprise win rate does not match paper_performance.json")

    watchlist_count = _count_rows(watchlist, "rows")
    if watchlist_count is not None and kpi.get("watchlist_count") != watchlist_count:
        errors.append("Enterprise watchlist count does not match current watchlist_report.json")
    if watchlist and watchlist.get("freshness_status") != "CURRENT_CYCLE":
        warnings.append("Watchlist is not marked CURRENT_CYCLE")

    position_count = portfolio.get("position_count") if portfolio else None
    if position_count is not None and kpi.get("position_count") != position_count:
        errors.append("Enterprise position count does not match paper portfolio summary")
    if positions and isinstance(positions.get("positions"), list) and position_count is not None:
        if len(positions["positions"]) != position_count:
            errors.append("Paper position detail count does not match portfolio summary")

    market_status = market.get("status") if market else None
    if market_status not in {"AVAILABLE", "CURRENT", "SUCCESS"}:
        warnings.append("Market-data refresh is not currently reported AVAILABLE/CURRENT/SUCCESS")

    return {
        "schema_version": "1.0",
        "strategy_id": STRATEGY_ID,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "read_only": True,
        "overall_status": "PASS" if not errors else "FAIL",
        "authoritative_values": {
            "allocated_capital": kpi.get("allocated_capital"),
            "allocation_source": kpi.get("allocation_source"),
            "opportunity_quality": oq,
            "committee_opportunity_quality": committee_oq,
            "entry_score": entry_score,
            "watchlist_count": watchlist_count,
            "position_count": position_count,
            "portfolio_value": portfolio.get("portfolio_value") if portfolio else None,
            "unrealized_pnl": portfolio.get("unrealized_pnl") if portfolio else None,
            "completed_trade_count": closed_trade_count,
            "win_rate_percent": authoritative_win_rate,
            "market_data_status": market_status,
        },
        "provenance": {
            "allocated_capital": "enterprise_strategy_kpis.json allocation provenance (externally governed)",
            "opportunity_quality": "opportunity_quality_report.json",
            "committee_opportunity_quality": "swing_committee_runtime_evidence.json",
            "entry_score": "swing_committee_runtime_evidence.json",
            "watchlist_count": "watchlist_report.json",
            "positions_and_portfolio": "paper_ledger/paper_portfolio_summary.json + paper_portfolio_positions.json",
            "win_rate_percent": "paper_ledger/paper_performance.json completed paper trades only",
            "market_data_status": "market_data_refresh_status.json",
        },
        "safety": safety,
        "errors": errors,
        "warnings": warnings,
    }


def write_runtime_evidence_authority_audit(payload: Mapping[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit authoritative Swing runtime evidence.")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--output", default="results/runtime_evidence_authority_audit.json")
    args = parser.parse_args()
    payload = build_runtime_evidence_authority_audit(args.results_dir)
    write_runtime_evidence_authority_audit(payload, args.output)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

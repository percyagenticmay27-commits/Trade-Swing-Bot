"""Publish the complete paper-only Swing evidence package for AI CIO consumption.

Version 2.1 builds on the validated v2 KPI payload and adds deterministic,
read-only dashboard sections plus an explicit artifact contract. It does not
modify strategy calculations, place orders, move capital, or import host code.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .enterprise_strategy_kpi_publisher import (
    DEFAULT_STRATEGY_ALLOCATIONS_PATH,
    STRATEGY_ID,
    _find_numeric,
    _holdings,
    _load_json,
    _require_safe_source,
    build_enterprise_strategy_kpis,
    validate_enterprise_strategy_kpis,
)

MODULE_NAME = "enterprise_strategy_kpi_publisher_v21"
MODULE_VERSION = "2.1.6"
SCHEMA_VERSION = "2.1"
KPI_CONTRACT_VERSION = "2.1"

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False

ARTIFACT_SPECS = (
    ("portfolio_allocations", "PORTFOLIO_ALLOCATIONS", "portfolio_allocations.json"),
    ("executive_dashboard", "EXECUTIVE_DASHBOARD", "executive_dashboard.json"),
    ("opportunity_quality", "OPPORTUNITY_QUALITY", "opportunity_quality_report.json"),
    ("watchlist", "WATCHLIST", "watchlist_report.json"),
    ("paper_portfolio_summary", "PAPER_PORTFOLIO_SUMMARY", "paper_ledger/paper_portfolio_summary.json"),
    ("paper_portfolio_positions", "PAPER_HOLDINGS", "paper_ledger/paper_portfolio_positions.json"),
    ("managed_trade_history", "TRADE_HISTORY", "paper_ledger/managed_trade_history.json"),
    ("trade_history_summary", "TRADE_HISTORY_SUMMARY", "paper_ledger/trade_history_summary.json"),
    ("closed_positions", "CLOSED_POSITIONS", "paper_ledger/closed_positions.json"),
    ("paper_performance", "PERFORMANCE_ANALYTICS", "paper_ledger/paper_performance.json"),
)

_LEGACY_ALLOCATION_VALIDATION_ERRORS = {
    "allocation_source must identify accepted allocation evidence",
    "allocation provenance source must match allocation_source",
}

_ACCEPTED_PORTFOLIO_VALUATION_SOURCES = {
    "PAPER_LEDGER_MARK_TO_MARKET",
    "PAPER_LEDGER_SPLIT_ADJUSTED_MARK_TO_MARKET",
}


def _artifact_contract(results_dir: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for artifact_id, artifact_type, relative_path in ARTIFACT_SPECS:
        path = results_dir / relative_path
        output.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "path": str(path.resolve()),
                "relative_path": relative_path,
                "format": "JSON",
                "scope": "STRATEGY",
                "authoritative": True,
                "required": False,
                "available": path.is_file(),
            }
        )
    return output


def _load_optional(results_dir: Path, relative_path: str) -> dict[str, Any] | None:
    return _load_json(results_dir / relative_path)


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _current_opportunity_score(payload: Mapping[str, Any] | None) -> float | None:
    direct = _find_numeric(payload, ("opportunity_quality_score", "opportunity_quality", "score"))
    if direct is not None:
        return direct
    rows = payload.get("rows") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return None
    scores: list[float] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        value = _find_numeric(row, ("opportunity_quality_score", "opportunity_quality", "score"))
        if value is not None:
            scores.append(value)
    return max(scores) if scores else None


def _apply_current_paper_portfolio(
    base: dict[str, Any],
    summary: Mapping[str, Any] | None,
    positions: Mapping[str, Any] | None,
    warnings: list[str],
) -> None:
    if not summary:
        return
    _require_safe_source(summary, "paper_portfolio_summary")
    valuation_source = str(summary.get("valuation_source", "")).strip()
    if valuation_source not in _ACCEPTED_PORTFOLIO_VALUATION_SOURCES:
        return

    allocated = _finite(base.get("allocated_capital"))
    account_capital = _finite(summary.get("account_capital"))
    if allocated is None or account_capital is None or abs(allocated - account_capital) > 0.01:
        raise ValueError("current paper portfolio account_capital must match governed SWING-001 allocation")

    required = {
        "portfolio_value": _finite(summary.get("portfolio_value")),
        "cash_balance": _finite(summary.get("cash_balance")),
        "invested_capital": _finite(summary.get("invested_capital")),
        "positions_market_value": _finite(summary.get("positions_market_value")),
        "unrealized_pnl": _finite(summary.get("unrealized_pnl")),
        "portfolio_return_percent": _finite(summary.get("portfolio_return_percent")),
    }
    position_count = summary.get("position_count")
    if any(value is None for value in required.values()) or not isinstance(position_count, int) or position_count < 0:
        return

    holdings = _holdings(positions)
    if positions is not None and len(holdings) != position_count:
        warnings.append("Detailed holdings count does not match the current paper portfolio position count.")

    base.update(
        {
            **required,
            "position_count": position_count,
            "open_positions": holdings,
            "portfolio_value_source": valuation_source,
        }
    )


def build_enterprise_strategy_kpis_v21(
    results_dir: str | Path = "results",
    *,
    strategy_allocations: Mapping[str, Any],
    strategy_allocations_source: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(results_dir)
    base = build_enterprise_strategy_kpis(
        root,
        strategy_allocations=strategy_allocations,
        strategy_allocations_source=strategy_allocations_source,
    )

    trade_history = _load_optional(root, "paper_ledger/managed_trade_history.json")
    closed_positions = _load_optional(root, "paper_ledger/closed_positions.json")
    executive = _load_optional(root, "executive_dashboard.json")
    opportunity = _load_optional(root, "opportunity_quality_report.json")
    watchlist = _load_optional(root, "watchlist_report.json")
    portfolio_summary = _load_optional(root, "paper_ledger/paper_portfolio_summary.json")
    paper_positions = _load_optional(root, "paper_ledger/paper_portfolio_positions.json")

    artifacts = _artifact_contract(root)
    available_artifacts = [item["artifact_id"] for item in artifacts if item["available"]]
    missing_optional_artifacts = [item["artifact_id"] for item in artifacts if not item["available"]]

    warnings = list(base.get("warnings", []))
    if missing_optional_artifacts:
        warnings.append(
            "Optional evidence unavailable: " + ", ".join(sorted(missing_optional_artifacts))
        )

    _apply_current_paper_portfolio(base, portfolio_summary, paper_positions, warnings)
    current_opportunity_score = _current_opportunity_score(opportunity)
    if current_opportunity_score is not None:
        base["opportunity_quality"] = current_opportunity_score

    allocation_provenance = dict(base.get("allocation_provenance", {}))
    portfolio_section = {
        "allocated_capital": base.get("allocated_capital"),
        "allocation_provenance": allocation_provenance,
        "portfolio_value": base.get("portfolio_value"),
        "portfolio_value_source": base.get("portfolio_value_source"),
        "cash_balance": base.get("cash_balance"),
        "invested_capital": base.get("invested_capital"),
        "positions_market_value": base.get("positions_market_value"),
        "position_count": base.get("position_count"),
        "portfolio_return_percent": base.get("portfolio_return_percent"),
    }
    holdings_section = {
        "position_count": base.get("position_count"),
        "open_positions": base.get("open_positions", []),
    }
    performance_section = {
        "realized_pnl": base.get("realized_pnl"),
        "unrealized_pnl": base.get("unrealized_pnl"),
        "total_pnl": base.get("total_pnl"),
        "portfolio_return_percent": base.get("portfolio_return_percent"),
        "trade_count": base.get("trade_count"),
        "closed_trade_count": base.get("closed_trade_count"),
        "win_rate_percent": base.get("win_rate_percent"),
        "analytics": base.get("performance"),
    }
    strategy_intelligence_section = {
        "opportunity_quality": base.get("opportunity_quality"),
        "watchlist_count": base.get("watchlist_count"),
        "opportunity_quality_evidence": opportunity,
        "watchlist_evidence": watchlist,
        "executive_dashboard_evidence": executive,
    }
    trade_history_section = {
        "summary": _load_optional(root, "paper_ledger/trade_history_summary.json"),
        "events": trade_history,
        "closed_positions": closed_positions,
    }

    payload = dict(base)
    payload.update(
        {
            "schema_version": SCHEMA_VERSION,
            "kpi_contract_version": KPI_CONTRACT_VERSION,
            "module_name": MODULE_NAME,
            "module_version": MODULE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "allocation_provenance": allocation_provenance,
            "portfolio": portfolio_section,
            "holdings": holdings_section,
            "performance_summary": performance_section,
            "strategy_intelligence": strategy_intelligence_section,
            "trade_history": trade_history_section,
            "dashboard_sections": {
                "allocation_provenance": allocation_provenance,
                "portfolio": portfolio_section,
                "holdings": holdings_section,
                "performance": performance_section,
                "watchlist": {
                    "count": base.get("watchlist_count"),
                    "evidence": watchlist,
                },
                "opportunity_quality": {
                    "score": base.get("opportunity_quality"),
                    "evidence": opportunity,
                },
            },
            "artifact_contract": artifacts,
            "available_artifacts": sorted(available_artifacts),
            "missing_optional_artifacts": sorted(missing_optional_artifacts),
            "artifacts": len(available_artifacts),
            "warnings": sorted(set(warnings)),
        }
    )
    return payload


def validate_enterprise_strategy_kpis_v21(payload: Mapping[str, Any]) -> tuple[str, ...]:
    provenance = payload.get("allocation_provenance")
    provenance_is_mapping = isinstance(provenance, Mapping)

    legacy_payload = dict(payload)
    legacy_payload["kpi_contract_version"] = "2.0"
    legacy_errors = validate_enterprise_strategy_kpis(legacy_payload)
    errors = [
        error
        for error in legacy_errors
        if error not in _LEGACY_ALLOCATION_VALIDATION_ERRORS
    ]

    if payload.get("strategy_id") != STRATEGY_ID:
        errors.append("strategy_id must be SWING-001")
    if payload.get("kpi_contract_version") != KPI_CONTRACT_VERSION:
        errors.append("kpi_contract_version must be 2.1")

    if not provenance_is_mapping:
        errors.append("allocation_provenance must be an object")
    else:
        required_fields = (
            "allocated_capital",
            "allocation_source",
            "allocation_evidence_schema",
            "allocation_source_json_path",
            "allocation_field",
        )
        for field in required_fields:
            if field not in provenance or provenance.get(field) in (None, ""):
                errors.append(f"allocation_provenance missing required field: {field}")

        provenance_source = provenance.get("allocation_source")
        payload_source = payload.get("allocation_source")
        if not isinstance(payload_source, str) or not payload_source.strip():
            errors.append("allocation_source must identify accepted allocation evidence")
        if not isinstance(provenance_source, str) or not provenance_source.strip():
            errors.append("allocation_provenance allocation_source is required")
        if provenance_source != payload_source:
            errors.append("allocation provenance source must match allocation_source")

        provenance_capital = provenance.get("allocated_capital")
        payload_capital = payload.get("allocated_capital")
        try:
            capital_matches = abs(float(provenance_capital) - float(payload_capital)) <= 0.01
        except (TypeError, ValueError):
            capital_matches = False
        if not capital_matches:
            errors.append("allocation_provenance allocated_capital must match allocated_capital")

    for section in (
        "portfolio",
        "holdings",
        "performance_summary",
        "strategy_intelligence",
        "trade_history",
        "dashboard_sections",
    ):
        if not isinstance(payload.get(section), Mapping):
            errors.append(f"{section} must be an object")

    contract = payload.get("artifact_contract")
    if not isinstance(contract, list):
        errors.append("artifact_contract must be a list")
    else:
        ids = [item.get("artifact_id") for item in contract if isinstance(item, Mapping)]
        if ids != sorted(set(ids)):
            errors.append("artifact IDs must be deterministic, sorted, and unique")
        for item in contract:
            if not isinstance(item, Mapping):
                errors.append("artifact contract entries must be objects")
                continue
            if item.get("scope") != "STRATEGY":
                errors.append("artifact scope must be STRATEGY")
            if item.get("required") is not False:
                errors.append("runtime evidence artifacts must remain optional")
            if not Path(str(item.get("path", ""))).is_absolute():
                errors.append("artifact paths must be absolute")

    return tuple(sorted(set(errors)))


def write_enterprise_strategy_kpis_v21(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    output_payload = dict(payload)
    errors = validate_enterprise_strategy_kpis_v21(output_payload)
    if errors:
        raise ValueError("Invalid Swing Enterprise KPI v2.1 evidence: " + "; ".join(errors))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(output_payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def build_and_write_enterprise_strategy_kpis_v21(
    results_dir: str | Path = "results",
    output_path: str | Path = "results/enterprise_strategy_kpis.json",
    *,
    strategy_allocations_path: str | Path = DEFAULT_STRATEGY_ALLOCATIONS_PATH,
) -> Path:
    allocation_path = Path(strategy_allocations_path)
    allocations = _load_json(allocation_path)
    if allocations is None:
        raise FileNotFoundError(f"Strategy allocation evidence not found: {allocation_path}")
    payload = build_enterprise_strategy_kpis_v21(
        results_dir,
        strategy_allocations=allocations,
        strategy_allocations_source=allocation_path,
    )
    return write_enterprise_strategy_kpis_v21(payload, output_path)

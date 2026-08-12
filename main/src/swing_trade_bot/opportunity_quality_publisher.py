"""Publish canonical Opportunity Quality evidence for the paper-only Swing Bot.

This adapter does not recalculate Opportunity Quality. It validates and summarizes
the authoritative opportunity_quality_report.json produced by
opportunity_quality_engine.py, then atomically publishes results/opportunity_quality.json
for Enterprise KPI and AI CIO consumption.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

MODULE_NAME = "opportunity_quality_publisher"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
SOURCE_FILENAME = "opportunity_quality_report.json"
OUTPUT_FILENAME = "opportunity_quality.json"

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DIRECT_DATABASE_WRITES = False


def _finite_score(value: object, field: str) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(score) or score < 0 or score > 100:
        raise ValueError(f"{field} must be finite and between 0 and 100")
    return score


def _load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Opportunity Quality report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Opportunity Quality report must be a JSON object")
    return payload


def _validate_source(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("paper_trade_mode must be true")
    if payload.get("entry_score_display_only") is not True:
        raise ValueError("entry_score_display_only must be true")
    if payload.get("entry_score_not_part_of_opportunity_quality") is not True:
        raise ValueError("Entry Score must remain excluded from Opportunity Quality")

    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"rows[{index}] must be an object")
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError(f"rows[{index}].symbol is required")
        if symbol in seen:
            raise ValueError(f"duplicate symbol in Opportunity Quality report: {symbol}")
        seen.add(symbol)
        score = _finite_score(row.get("opportunity_quality_score"), f"rows[{index}].opportunity_quality_score")
        normalized.append(
            {
                "symbol": symbol,
                "opportunity_quality_score": round(score, 6),
                "opportunity_quality_level": str(row.get("opportunity_quality_level", "")).strip().upper(),
                "entry_score": _finite_score(row.get("entry_score", 0), f"rows[{index}].entry_score"),
                "entry_score_gate_passed": bool(row.get("entry_score_gate_passed", False)),
            }
        )
    return normalized


def build_opportunity_quality_evidence(
    source_path: str | Path = Path("results") / SOURCE_FILENAME,
) -> dict[str, Any]:
    """Build canonical read-only Opportunity Quality evidence."""
    source = Path(source_path)
    report = _load_report(source)
    rows = _validate_source(report)
    ranked = sorted(rows, key=lambda row: (-row["opportunity_quality_score"], row["symbol"]))

    if ranked:
        top = ranked[0]
        average = round(sum(row["opportunity_quality_score"] for row in ranked) / len(ranked), 6)
        overall_score: float | None = top["opportunity_quality_score"]
        overall_level: str | None = top["opportunity_quality_level"]
        status = "AVAILABLE"
        warnings: list[str] = []
    else:
        top = None
        average = None
        overall_score = None
        overall_level = None
        status = "PARTIAL"
        warnings = ["Opportunity Quality report contains no opportunity rows."]

    return {
        "schema_version": SCHEMA_VERSION,
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_report": str(source),
        "source_system_mode": report.get("system_mode"),
        "opportunity_quality_score": overall_score,
        "opportunity_quality_level": overall_level,
        "top_opportunity": top,
        "average_opportunity_quality_score": average,
        "opportunity_count": len(ranked),
        "ranked_opportunities": ranked,
        "component_weights": report.get("component_weights", {}),
        "entry_score_display_only": True,
        "entry_score_not_part_of_opportunity_quality": True,
        "missing_evidence_rule": "missing evidence = 0",
        "evidence_status": status,
        "warnings": warnings,
        "errors": [],
        "paper_trade_mode": True,
        "paper_compatible": True,
        "advisory_only": True,
        "reporting_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "direct_database_writes": False,
    }


def validate_opportunity_quality_evidence(payload: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be 1.0")
    if payload.get("entry_score_display_only") is not True:
        errors.append("entry_score_display_only must be true")
    if payload.get("entry_score_not_part_of_opportunity_quality") is not True:
        errors.append("entry_score_not_part_of_opportunity_quality must be true")
    if payload.get("evidence_status") not in {"AVAILABLE", "PARTIAL"}:
        errors.append("unsupported evidence_status")
    ranked = payload.get("ranked_opportunities")
    if not isinstance(ranked, list):
        errors.append("ranked_opportunities must be a list")
    if payload.get("opportunity_count") != (len(ranked) if isinstance(ranked, list) else None):
        errors.append("opportunity_count must match ranked_opportunities")
    for field in ("paper_trade_mode", "paper_compatible", "advisory_only", "reporting_only"):
        if payload.get(field) is not True:
            errors.append(f"{field} must be true")
    for field in (
        "live_trading_enabled", "broker_execution_enabled", "order_placement_enabled",
        "capital_movement_enabled", "direct_database_writes",
    ):
        if payload.get(field) is not False:
            errors.append(f"{field} must be false")
    return tuple(errors)


def write_opportunity_quality_evidence(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    errors = validate_opportunity_quality_evidence(payload)
    if errors:
        raise ValueError("Invalid Opportunity Quality evidence: " + "; ".join(errors))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(dict(payload), output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def build_and_write_opportunity_quality_evidence(
    source_path: str | Path = Path("results") / SOURCE_FILENAME,
    output_path: str | Path = Path("results") / OUTPUT_FILENAME,
) -> Path:
    return write_opportunity_quality_evidence(
        build_opportunity_quality_evidence(source_path),
        output_path,
    )

"""Authoritative, paper-only Swing decision journal publication.

The journal presents current position and candidate decisions without turning
allocation/rebalance suggestions into trades.  It never creates BUY, SELL, or
closed-position evidence and has no execution or capital-movement capability.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

STRATEGY_ID = "SWING-001"
MODULE_NAME = "swing_decision_journal_report"
MODULE_VERSION = "1.0.0"
PAPER_TRADE_MODE = True
ADVISORY_ONLY = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False

JSON_NAME = "swing_decision_journal_report.json"
MARKDOWN_NAME = "swing_decision_journal_report.md"
ALLOWED_DECISIONS = {"HOLD", "WAITING_FOR_ENTRY", "ENTRY_REVIEW", "EXIT_REVIEW"}


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _stamp(payload: Mapping[str, Any] | None) -> str | None:
    if payload:
        for key in ("generated_at_utc", "generated_at", "as_of_date"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _current(payload: Mapping[str, Any] | None, now: datetime, max_age_seconds: int) -> tuple[bool, str]:
    if payload is None:
        return False, "MISSING"
    timestamp = _parse(_stamp(payload))
    if timestamp is None:
        return False, "TIMESTAMP_UNAVAILABLE"
    age = (now - timestamp).total_seconds()
    if age < -300:
        return False, "FUTURE_TIMESTAMP"
    if age > max_age_seconds:
        return False, "STALE"
    return True, "CURRENT"


def _safe_required(payload: Mapping[str, Any], name: str) -> None:
    identity = payload.get("strategy_id") or payload.get("plugin_id")
    if identity != STRATEGY_ID:
        raise ValueError(f"{name} identity must be SWING-001")
    if payload.get("paper_trade_mode") is not True or payload.get("advisory_only") is not True:
        raise ValueError(f"{name} must remain paper-only and advisory-only")


def _position_decisions(kpi: Mapping[str, Any], timestamp: str) -> list[dict[str, Any]]:
    analytics = kpi.get("trade_analytics")
    if not isinstance(analytics, Mapping):
        raise ValueError("Enterprise KPI evidence must contain trade_analytics")
    rows = analytics.get("open_positions")
    if not isinstance(rows, list):
        raise ValueError("trade_analytics.open_positions must be a list")
    output: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("open position evidence must contain objects")
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not symbol or str(raw.get("position_status", "OPEN")).upper() != "OPEN":
            raise ValueError("authoritative open-position identity is invalid")
        output.append({
            "decision_id": f"SWING-POSITION-{symbol}-{timestamp[:10]}",
            "decision_scope": "OPEN_POSITION",
            "symbol": symbol,
            "current_state": "OPEN",
            "current_decision": "HOLD",
            "current_owner": str(raw.get("active_strategy") or "STRATEGY_UNREPORTED"),
            "rationale": "Authoritative paper position remains open; no current authoritative exit decision is reported.",
            "alternatives_considered": [],
            "evidence_timestamp": timestamp,
            "evidence_sources": ["results/enterprise_strategy_kpis.json#trade_analytics.open_positions"],
            "timeline": [{
                "sequence": 1,
                "owner": str(raw.get("active_strategy") or "STRATEGY_UNREPORTED"),
                "status": "HOLD",
                "reason_codes": ["AUTHORITATIVE_OPEN_POSITION", "NO_AUTHORITATIVE_EXIT_DECISION"],
                "evidence_timestamp": timestamp,
            }],
            "paper_trade_mode": True,
            "advisory_only": True,
        })
    return output


def _candidate_decision(runtime: Mapping[str, Any], trace: Mapping[str, Any]) -> dict[str, Any]:
    if runtime.get("evaluation_cycle_id") != trace.get("evaluation_cycle_id"):
        raise ValueError("committee runtime and trace evaluation_cycle_id do not match")
    symbol = str(runtime.get("symbol") or "").strip().upper()
    if not symbol or symbol != str(trace.get("symbol") or "").strip().upper():
        raise ValueError("committee runtime and trace symbol do not match")
    final = str(trace.get("final_status") or runtime.get("final_status") or "").upper()
    decision = {
        "WAIT": "WAITING_FOR_ENTRY",
        "ELIGIBLE_FOR_ALLOCATION": "ENTRY_REVIEW",
        "REVIEW": "EXIT_REVIEW",
        "HOLD": "HOLD",
    }.get(final)
    if decision is None:
        # Rejected candidates remain evidence, not invented entry instructions.
        decision = "WAITING_FOR_ENTRY"
    steps = trace.get("committee_steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("committee decision trace must contain committee_steps")
    timeline = []
    for raw in sorted(steps, key=lambda item: int(item.get("sequence", 999)) if isinstance(item, Mapping) else 999):
        if not isinstance(raw, Mapping):
            raise ValueError("committee_steps must contain objects")
        timeline.append({
            "sequence": raw.get("sequence"),
            "owner": raw.get("committee_id"),
            "status": raw.get("status"),
            "reason_codes": list(raw.get("reason_codes") or []),
            "evidence": dict(raw.get("evidence") or {}),
            "source_artifacts": list(raw.get("source_artifacts") or []),
        })
    controlling = next((row for row in reversed(timeline) if row["status"] not in {"PASS", "NOT_APPLICABLE", "SKIPPED"}), timeline[-1])
    reasons = controlling.get("reason_codes") or [f"FINAL_STATUS_{final or 'UNREPORTED'}"]
    timestamp = str(trace.get("generated_at_utc") or runtime.get("generated_at_utc"))
    return {
        "decision_id": str(trace.get("decision_trace_id") or runtime.get("evaluation_cycle_id")),
        "decision_scope": "CANDIDATE",
        "symbol": symbol,
        "current_state": final or "WAIT",
        "current_decision": decision,
        "current_owner": controlling.get("owner"),
        "rationale": "; ".join(str(item) for item in reasons),
        "alternatives_considered": [],
        "evidence_timestamp": timestamp,
        "evidence_sources": sorted(set(list(trace.get("source_artifacts") or []) + ["results/swing_committee_decision_trace.json", "results/swing_committee_runtime_evidence.json"])),
        "timeline": timeline,
        "paper_trade_mode": True,
        "advisory_only": True,
    }


def build_swing_decision_journal_report(
    results_dir: str | Path = "results", *,
    kpi_payload: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    max_age_seconds: int = 172800,
) -> dict[str, Any]:
    root = Path(results_dir)
    generated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    generated_text = generated.isoformat().replace("+00:00", "Z")
    kpi = dict(kpi_payload) if kpi_payload is not None else _load(root / "enterprise_strategy_kpis.json")
    cycle = _load(root / "swing_daily_cycle_report.json")
    if kpi is None or cycle is None:
        raise FileNotFoundError("Current Enterprise KPI and Swing cycle evidence are required")
    _safe_required(kpi, "Enterprise KPI evidence")
    _safe_required(cycle, "Swing cycle evidence")
    for name, payload in (("enterprise_strategy_kpis.json", kpi), ("swing_daily_cycle_report.json", cycle)):
        current, status = _current(payload, generated, max_age_seconds)
        if not current:
            raise ValueError(f"Required decision evidence is not current: {name} ({status})")

    kpi_stamp = _stamp(kpi) or generated_text
    positions = _position_decisions(kpi, kpi_stamp)
    runtime = _load(root / "swing_committee_runtime_evidence.json")
    trace = _load(root / "swing_committee_decision_trace.json")
    warnings: list[str] = []
    candidates: list[dict[str, Any]] = []
    if runtime is None or trace is None:
        warnings.append("Current matched committee runtime and trace evidence is unavailable; candidate decisions are not reported.")
    else:
        for name, payload in (("committee runtime", runtime), ("committee trace", trace)):
            identity = payload.get("plugin_id")
            if identity not in (None, STRATEGY_ID):
                raise ValueError(f"{name} plugin identity must be SWING-001")
            if payload.get("paper_trade_mode") is not True or payload.get("advisory_only") is not True:
                raise ValueError(f"{name} must remain paper-only and advisory-only")
            current, status = _current(payload, generated, max_age_seconds)
            if not current:
                warnings.append(f"Excluded {name}: {status}")
        if not warnings:
            candidates.append(_candidate_decision(runtime, trace))

    decisions = sorted([*positions, *candidates], key=lambda row: (0 if row["decision_scope"] == "OPEN_POSITION" else 1, row["symbol"], row["decision_id"]))
    if any(row["current_decision"] not in ALLOWED_DECISIONS for row in decisions):
        raise ValueError("Decision journal contains a prohibited decision")
    return {
        "schema_version": "1.0",
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_at_utc": generated_text,
        "paper_trade_mode": PAPER_TRADE_MODE,
        "advisory_only": ADVISORY_ONLY,
        "live_trading_enabled": LIVE_TRADING_ENABLED,
        "broker_execution_enabled": BROKER_EXECUTION_ENABLED,
        "order_placement_enabled": ORDER_PLACEMENT_ENABLED,
        "capital_movement_enabled": CAPITAL_MOVEMENT_ENABLED,
        "decision_authority_policy": "CURRENT_MATCHED_AUTHORITATIVE_EVIDENCE_ONLY",
        "position_decision_count": len(positions),
        "candidate_decision_count": len(candidates),
        "decision_count": len(decisions),
        "position_decisions": positions,
        "candidate_decisions": candidates,
        "decisions": decisions,
        "evidence_warnings": sorted(set(warnings)),
        "evaluation_status": "COMPLETE" if not warnings else "COMPLETE_WITH_EVIDENCE_WARNINGS",
        "no_decisions_message": "Current authoritative Swing evidence was evaluated and no reportable decisions were found." if not decisions else None,
        "excluded_planning_sources": ["results/rebalance_actions.json"],
    }


def _atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def write_swing_decision_journal_report(report: Mapping[str, Any], output_dir: str | Path = "results") -> tuple[Path, Path]:
    root = Path(output_dir)
    json_path, md_path = root / JSON_NAME, root / MARKDOWN_NAME
    _atomic(json_path, json.dumps(dict(report), indent=2, sort_keys=True) + "\n")
    lines = ["# Swing Decision Journal", "", f"- Strategy: {report.get('strategy_id')}", f"- Decisions: {report.get('decision_count')}", "", "## Current Decisions", ""]
    decisions = report.get("decisions")
    if isinstance(decisions, list) and decisions:
        for row in decisions:
            lines.append(f"- {row.get('symbol')} | {row.get('decision_scope')} | {row.get('current_decision')} | {row.get('current_owner')} | {row.get('rationale')}")
    else:
        lines.append(str(report.get("no_decisions_message")))
    _atomic(md_path, "\n".join(lines) + "\n")
    return json_path, md_path

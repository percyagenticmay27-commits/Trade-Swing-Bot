"""Authoritative paper-only Swing strategy alerts publication.

This module converts only current, identity-consistent operational evidence into
advisory alerts. Legacy dashboard risk flags are evaluation inputs, never alert
authority, because their source reports may be stale.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

STRATEGY_ID = "SWING-001"
MODULE_NAME = "swing_strategy_alerts_report"
MODULE_VERSION = "1.0"
PAPER_TRADE_MODE = True
ADVISORY_ONLY = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False

JSON_NAME = "swing_strategy_alerts_report.json"
CSV_NAME = "swing_strategy_alerts_report.csv"
MARKDOWN_NAME = "swing_strategy_alerts_report.md"


def _timestamp(payload: Mapping[str, Any]) -> str | None:
    for key in ("generated_at_utc", "generated_at", "as_of_utc", "as_of_date"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _current(
    payload: Mapping[str, Any] | None,
    *,
    now: datetime,
    max_age_seconds: int,
) -> tuple[bool, str]:
    if payload is None:
        return False, "MISSING"
    stamp = _parse_timestamp(_timestamp(payload))
    if stamp is None:
        return False, "TIMESTAMP_UNAVAILABLE"
    age = (now - stamp).total_seconds()
    if age < -300:
        return False, "FUTURE_TIMESTAMP"
    if age > max_age_seconds:
        return False, "STALE"
    return True, "CURRENT"


def _messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    messages: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            messages.append(item.strip())
        elif isinstance(item, Mapping):
            text = item.get("message") or item.get("error") or item.get("warning")
            if isinstance(text, str) and text.strip():
                messages.append(text.strip())
    return messages


def _alert(
    *,
    category: str,
    severity: str,
    message: str,
    source: str,
    evidence_timestamp: str,
) -> dict[str, Any]:
    return {
        "strategy_id": STRATEGY_ID,
        "symbol": None,
        "alert_category": category,
        "severity": severity,
        "priority": "HIGH" if severity == "ERROR" else "MEDIUM",
        "status": "OPEN",
        "message": message,
        "recommended_review_action": "Review authoritative Swing evidence; no automatic action is permitted.",
        "evidence_source": source,
        "evidence_timestamp": evidence_timestamp,
        "paper_trade_mode": True,
        "advisory_only": True,
    }


def build_swing_strategy_alerts_report(
    results_dir: str | Path = "results",
    *,
    kpi_payload: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    max_age_seconds: int = 172800,
) -> dict[str, Any]:
    root = Path(results_dir)
    generated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    generated_text = generated.isoformat().replace("+00:00", "Z")

    kpi = dict(kpi_payload) if kpi_payload is not None else _load(root / "enterprise_strategy_kpis.json")
    cycle = _load(root / "swing_daily_cycle_report.json")
    health = _load(root / "operational_health_report.json")
    audit = _load(root / "runtime_evidence_authority_audit.json")
    dashboard = _load(root / "executive_dashboard.json")

    if kpi is None:
        raise FileNotFoundError("Authoritative Enterprise KPI evidence is required")
    if kpi.get("strategy_id") != STRATEGY_ID:
        raise ValueError("Enterprise KPI strategy_id must be SWING-001")
    if kpi.get("paper_trade_mode") is not True or kpi.get("advisory_only") is not True:
        raise ValueError("Enterprise KPI evidence must remain paper-only and advisory-only")

    evaluations: list[dict[str, Any]] = []
    evidence_warnings: list[str] = []
    alerts: list[dict[str, Any]] = []

    sources = (
        ("enterprise_strategy_kpis.json", kpi, True),
        ("swing_daily_cycle_report.json", cycle, True),
        ("operational_health_report.json", health, False),
        ("runtime_evidence_authority_audit.json", audit, False),
    )
    for name, payload, required in sources:
        is_current, status = _current(payload, now=generated, max_age_seconds=max_age_seconds)
        evaluations.append({
            "source": name,
            "required": required,
            "status": status,
            "evidence_timestamp": _timestamp(payload) if payload else None,
        })
        if required and not is_current:
            raise ValueError(f"Required alert evidence is not current: {name} ({status})")
        if payload is not None and not is_current:
            evidence_warnings.append(f"Excluded {name}: {status}")
            continue
        if payload is None:
            if not required:
                evidence_warnings.append(f"Optional alert evidence unavailable: {name}")
            continue

        source_stamp = _timestamp(payload) or generated_text
        for message in _messages(payload.get("errors")):
            alerts.append(_alert(
                category="OPERATIONAL_EVIDENCE",
                severity="ERROR",
                message=message,
                source=name,
                evidence_timestamp=source_stamp,
            ))
        for message in _messages(payload.get("warnings")):
            alerts.append(_alert(
                category="OPERATIONAL_EVIDENCE",
                severity="WARNING",
                message=message,
                source=name,
                evidence_timestamp=source_stamp,
            ))

    dashboard_status = "MISSING"
    dashboard_reason = "Legacy dashboard unavailable"
    if dashboard is not None:
        position_count = kpi.get("position_count")
        dashboard_positions = (dashboard.get("summary") or {}).get("active_positions") if isinstance(dashboard.get("summary"), Mapping) else None
        dashboard_current, freshness = _current(
            dashboard, now=generated, max_age_seconds=max_age_seconds
        )
        if not dashboard_current:
            dashboard_status = "EXCLUDED"
            dashboard_reason = f"Legacy dashboard is not current: {freshness}"
        elif dashboard_positions != position_count:
            dashboard_status = "EXCLUDED"
            dashboard_reason = (
                "Legacy dashboard active_positions does not match authoritative "
                "Enterprise KPI position_count"
            )
        else:
            dashboard_status = "EVALUATED_NOT_AUTHORITY"
            dashboard_reason = "Legacy risk flags are not authoritative alert inputs"
    evaluations.append({
        "source": "executive_dashboard.json",
        "required": False,
        "status": dashboard_status,
        "evidence_timestamp": _timestamp(dashboard) if dashboard else None,
    })
    if dashboard_status == "EXCLUDED":
        evidence_warnings.append(dashboard_reason)

    unique = {
        (item["severity"], item["message"], item["evidence_source"]): item
        for item in alerts
    }
    ordered_alerts = sorted(
        unique.values(),
        key=lambda item: (
            0 if item["severity"] == "ERROR" else 1,
            item["evidence_source"],
            item["message"],
        ),
    )

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
        "alert_authority_policy": "CURRENT_AUTHORITATIVE_EVIDENCE_ONLY",
        "actionable_alert_count": len(ordered_alerts),
        "alerts": ordered_alerts,
        "evidence_warning_count": len(sorted(set(evidence_warnings))),
        "evidence_warnings": sorted(set(evidence_warnings)),
        "source_evaluations": evaluations,
        "evaluation_status": "COMPLETE" if not evidence_warnings else "COMPLETE_WITH_EVIDENCE_WARNINGS",
        "no_actionable_alerts_message": (
            "Current authoritative Swing evidence was evaluated and no actionable alerts were found."
            if not ordered_alerts
            else None
        ),
    }


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_swing_strategy_alerts_report(
    report: Mapping[str, Any],
    output_dir: str | Path = "results",
) -> tuple[Path, Path, Path]:
    root = Path(output_dir)
    json_path = root / JSON_NAME
    csv_path = root / CSV_NAME
    md_path = root / MARKDOWN_NAME

    _atomic_text(json_path, json.dumps(dict(report), indent=2, sort_keys=True) + "\n")

    rows = report.get("alerts")
    if not isinstance(rows, list):
        raise ValueError("alerts must be a list")
    columns = (
        "strategy_id", "symbol", "alert_category", "severity", "priority",
        "status", "message", "recommended_review_action", "evidence_source",
        "evidence_timestamp", "paper_trade_mode", "advisory_only",
    )
    temporary_csv = root / f".{CSV_NAME}.render"
    root.mkdir(parents=True, exist_ok=True)
    with temporary_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in columns})
    _atomic_text(csv_path, temporary_csv.read_text(encoding="utf-8"))
    temporary_csv.unlink()

    lines = [
        "# Swing Strategy Alerts",
        "",
        f"- Strategy: {report.get('strategy_id')}",
        f"- Generated: {report.get('generated_at_utc')}",
        f"- Actionable alerts: {report.get('actionable_alert_count')}",
        f"- Evidence warnings: {report.get('evidence_warning_count')}",
        "",
        "## Actionable Alerts",
        "",
    ]
    if rows:
        for row in rows:
            lines.append(
                f"- {row.get('severity')} | {row.get('symbol') or 'PORTFOLIO'} | "
                f"{row.get('message')} ({row.get('evidence_source')})"
            )
    else:
        lines.append(str(report.get("no_actionable_alerts_message")))
    lines.extend(["", "## Evidence Warnings", ""])
    warnings = report.get("evidence_warnings")
    if isinstance(warnings, list) and warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- None")
    _atomic_text(md_path, "\n".join(lines) + "\n")
    return json_path, csv_path, md_path


def build_and_write_swing_strategy_alerts_report(
    results_dir: str | Path = "results",
    *,
    now: datetime | None = None,
    max_age_seconds: int = 172800,
) -> tuple[Path, Path, Path]:
    report = build_swing_strategy_alerts_report(
        results_dir, now=now, max_age_seconds=max_age_seconds
    )
    return write_swing_strategy_alerts_report(report, results_dir)

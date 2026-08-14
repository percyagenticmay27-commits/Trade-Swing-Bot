"""Read-only operational health assessment for the scheduled Swing runtime.

The health layer consumes Swing-owned runtime evidence only. It does not execute
trades, refresh strategy data, modify the AI CIO host, or change portfolio state.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

STRATEGY_ID = "SWING-001"
MODULE_NAME = "swing_operational_health"
MODULE_VERSION = "1.0.0"
EASTERN = ZoneInfo("America/New_York")
SCHEDULE_HOUR = 18
SCHEDULE_MINUTE = 30
DEFAULT_GRACE_MINUTES = 90

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False

CRITICAL_WRITABLE_PATHS = (
    "watchlist_report.json",
    "portfolio_allocations.json",
    "enterprise_strategy_kpis.json",
    "paper_ledger/paper_portfolio_summary.json",
    "paper_ledger/managed_trade_history.json",
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def latest_expected_run_utc(now_utc: datetime) -> datetime:
    """Return the latest weekday 18:30 America/New_York scheduled run."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    local_now = now_utc.astimezone(EASTERN)
    candidate = local_now.replace(
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        second=0,
        microsecond=0,
    )
    if local_now < candidate:
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def _safety_ok(payload: dict[str, Any]) -> bool:
    return (
        payload.get("paper_trade_mode") is True
        and payload.get("live_trading_enabled") is False
        and payload.get("broker_execution_enabled") is False
        and payload.get("order_placement_enabled") is False
        and payload.get("capital_movement_enabled") is False
    )


def build_operational_health(
    results_dir: str | Path,
    *,
    now_utc: datetime | None = None,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> dict[str, Any]:
    """Assess current scheduled-runtime health from authoritative Swing evidence."""
    root = Path(results_dir).resolve()
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    status_path = root / "operational_runtime_status.json"
    cycle_path = root / "swing_daily_cycle_report.json"

    operational: dict[str, Any] | None = None
    cycle: dict[str, Any] | None = None

    if not status_path.is_file():
        errors.append("Missing operational_runtime_status.json")
    else:
        try:
            operational = _load_json(status_path)
        except Exception as exc:
            errors.append(f"Invalid operational runtime status: {exc}")

    if not cycle_path.is_file():
        errors.append("Missing swing_daily_cycle_report.json")
    else:
        try:
            cycle = _load_json(cycle_path)
        except Exception as exc:
            errors.append(f"Invalid Swing daily cycle report: {exc}")

    if operational is not None:
        checks["operational_status"] = operational.get("status")
        checks["authority_audit_status"] = operational.get("authority_audit_status")
        checks["cycle_exit_code"] = operational.get("cycle_exit_code")
        checks["paper_safety"] = _safety_ok(operational)
        if operational.get("status") != "SUCCESS":
            errors.append("Last operational runtime status is not SUCCESS")
        if operational.get("authority_audit_status") != "PASS":
            errors.append("Last runtime authority audit is not PASS")
        if operational.get("cycle_exit_code") != 0:
            errors.append("Last operational cycle exit code is nonzero")
        if not _safety_ok(operational):
            errors.append("Operational runtime paper-safety flags are invalid")

        finished = _parse_utc(operational.get("finished_at_utc"))
        expected = latest_expected_run_utc(now)
        grace = timedelta(minutes=max(0, int(grace_minutes)))
        checks["finished_at_utc"] = finished.isoformat().replace("+00:00", "Z") if finished else None
        checks["latest_expected_run_utc"] = expected.isoformat().replace("+00:00", "Z")
        checks["freshness_grace_minutes"] = max(0, int(grace_minutes))
        fresh = finished is not None and finished >= expected - grace
        checks["scheduled_run_fresh"] = fresh
        if finished is None:
            errors.append("Operational runtime finished_at_utc is missing or invalid")
        elif not fresh:
            errors.append("Scheduled Swing runtime evidence is stale")

    if cycle is not None:
        stage_count = cycle.get("stage_count")
        passed_stage_count = cycle.get("passed_stage_count")
        checks["cycle_status"] = cycle.get("cycle_status")
        checks["registration_published"] = cycle.get("registration_published")
        checks["stage_count"] = stage_count
        checks["passed_stage_count"] = passed_stage_count
        if cycle.get("cycle_status") != "COMPLETE":
            errors.append("Last Swing daily cycle is not COMPLETE")
        if stage_count is None or passed_stage_count != stage_count:
            errors.append("Last Swing daily cycle did not pass every stage")
        if cycle.get("registration_published") is not True:
            errors.append("Last Swing registration was not published")

    writable_failures: list[str] = []
    missing_writable: list[str] = []
    for relative in CRITICAL_WRITABLE_PATHS:
        path = root / relative
        if not path.exists():
            missing_writable.append(relative)
            continue
        if not os.access(path, os.R_OK | os.W_OK):
            writable_failures.append(relative)
    checks["critical_runtime_files_writable"] = not writable_failures
    checks["critical_runtime_writable_failures"] = writable_failures
    checks["critical_runtime_missing_files"] = missing_writable
    if writable_failures:
        errors.append(
            "Critical Swing runtime artifacts are not readable/writable by the service user: "
            + ", ".join(writable_failures)
        )
    if missing_writable:
        warnings.append(
            "Critical runtime artifacts not yet present: " + ", ".join(missing_writable)
        )

    return {
        "schema_version": "1.0",
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "status": "HEALTHY" if not errors else "UNHEALTHY",
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "paper_trade_mode": PAPER_TRADE_MODE,
        "live_trading_enabled": LIVE_TRADING_ENABLED,
        "broker_execution_enabled": BROKER_EXECUTION_ENABLED,
        "order_placement_enabled": ORDER_PLACEMENT_ENABLED,
        "capital_movement_enabled": CAPITAL_MOVEMENT_ENABLED,
        "read_only_assessment": True,
    }


def _atomic_write_json(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
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


def write_operational_health(
    results_dir: str | Path,
    *,
    output_path: str | Path | None = None,
    now_utc: datetime | None = None,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> tuple[dict[str, Any], Path]:
    root = Path(results_dir).resolve()
    payload = build_operational_health(root, now_utc=now_utc, grace_minutes=grace_minutes)
    destination = Path(output_path).resolve() if output_path is not None else root / "operational_health_report.json"
    return payload, _atomic_write_json(payload, destination)

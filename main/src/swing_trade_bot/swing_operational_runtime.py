"""Operational coordinator for scheduled paper-only Swing cycles.

This module wraps the existing authoritative Swing cycle without duplicating
market-data, strategy, allocation, ledger, or KPI engines. It adds only
operational concerns needed by a scheduler: overlap protection, status evidence,
and post-cycle authority validation.

It never connects to a broker, places orders, moves capital, or writes to the
Trade-Dividend-Bot repository.
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .runtime_evidence_authority_audit import build_runtime_evidence_authority_audit

STRATEGY_ID = "SWING-001"
MODULE_NAME = "swing_operational_runtime"
MODULE_VERSION = "1.0.0"

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


@contextmanager
def _exclusive_lock(lock_path: Path) -> Iterator[None]:
    """Fail closed when a scheduled Swing cycle is already running."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"Swing operational cycle is already running: {lock_path}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\nstarted_at_utc={_utc_now()}\n")
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def build_operational_status(
    *,
    started_at_utc: str,
    finished_at_utc: str,
    cycle_exit_code: int,
    audit: dict[str, Any] | None,
    error: str | None = None,
) -> dict[str, Any]:
    audit_status = audit.get("overall_status") if isinstance(audit, dict) else None
    success = cycle_exit_code == 0 and audit_status == "PASS" and error is None
    return {
        "schema_version": "1.0",
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "strategy_id": STRATEGY_ID,
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "status": "SUCCESS" if success else "FAILED",
        "cycle_exit_code": int(cycle_exit_code),
        "authority_audit_status": audit_status,
        "authority_audit_errors": list(audit.get("errors", [])) if isinstance(audit, dict) else [],
        "authority_audit_warnings": list(audit.get("warnings", [])) if isinstance(audit, dict) else [],
        "error": error,
        "paper_trade_mode": PAPER_TRADE_MODE,
        "live_trading_enabled": LIVE_TRADING_ENABLED,
        "broker_execution_enabled": BROKER_EXECUTION_ENABLED,
        "order_placement_enabled": ORDER_PLACEMENT_ENABLED,
        "capital_movement_enabled": CAPITAL_MOVEMENT_ENABLED,
    }


def run_operational_cycle(
    *,
    root: str | Path = ".",
    run_cycle: Callable[[], int],
) -> int:
    """Run the existing Swing cycle once, then verify authoritative evidence.

    ``run_cycle`` must be the existing authoritative launcher callable. Keeping it
    injected makes this coordinator testable without duplicating or importing host
    execution behavior.
    """
    repo_root = Path(root).resolve()
    results_dir = repo_root / "results"
    lock_path = results_dir / "operational_runtime.lock"
    status_path = results_dir / "operational_runtime_status.json"
    started = _utc_now()

    try:
        with _exclusive_lock(lock_path):
            cycle_exit = int(run_cycle())
            audit: dict[str, Any] | None = None
            error: str | None = None
            if cycle_exit == 0:
                audit = build_runtime_evidence_authority_audit(results_dir)
                if audit.get("overall_status") != "PASS":
                    error = "Post-cycle runtime evidence authority audit failed"
            else:
                error = f"Authoritative Swing cycle failed with exit code {cycle_exit}"

            status = build_operational_status(
                started_at_utc=started,
                finished_at_utc=_utc_now(),
                cycle_exit_code=cycle_exit,
                audit=audit,
                error=error,
            )
            _atomic_write_json(status, status_path)
            return 0 if status["status"] == "SUCCESS" else (cycle_exit or 1)
    except RuntimeError as exc:
        status = build_operational_status(
            started_at_utc=started,
            finished_at_utc=_utc_now(),
            cycle_exit_code=75,
            audit=None,
            error=str(exc),
        )
        _atomic_write_json(status, status_path)
        return 75
    except Exception as exc:
        status = build_operational_status(
            started_at_utc=started,
            finished_at_utc=_utc_now(),
            cycle_exit_code=1,
            audit=None,
            error=f"Operational runtime exception: {exc}",
        )
        _atomic_write_json(status, status_path)
        return 1

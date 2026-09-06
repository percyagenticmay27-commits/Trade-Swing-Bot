"""Optional user veto control for SWING-001 paper progression.

A veto is an exception/blocking control, never a prerequisite approval. Absence of
an active veto changes nothing. The immutable event history records ACTIVE and
RELEASED events; runtime filtering is Swing-owned and never writes to AI CIO.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

STRATEGY_ID = "SWING-001"
DEFAULT_LEDGER_PATH = Path("results/user_veto_ledger.json")
DEFAULT_RUNTIME_CANDIDATES = Path("results/discovery_candidates_runtime.csv")
DEFAULT_VETO_REPORT = Path("results/user_veto_status.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2)
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


def load_veto_ledger(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        return {
            "schema_version": "1.0",
            "strategy_id": STRATEGY_ID,
            "paper_trade_mode": True,
            "approval_required": False,
            "events": [],
        }
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("user veto ledger root must be an object")
    if payload.get("strategy_id") != STRATEGY_ID:
        raise ValueError("user veto ledger strategy_id must be SWING-001")
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("user veto ledger paper_trade_mode must be true")
    if payload.get("approval_required") is not False:
        raise ValueError("user veto ledger approval_required must be false")
    if not isinstance(payload.get("events"), list):
        raise ValueError("user veto ledger events must be a list")
    return payload


def active_vetoes(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    active: dict[str, dict[str, Any]] = {}
    for event in payload.get("events", []):
        if not isinstance(event, Mapping):
            continue
        symbol = str(event.get("symbol", "")).strip().upper()
        action = str(event.get("action", "")).strip().upper()
        if not symbol:
            continue
        if action == "VETO":
            active[symbol] = dict(event)
        elif action == "RELEASE":
            active.pop(symbol, None)
    return active


def append_veto_event(
    path: str | Path,
    *,
    symbol: str,
    action: str,
    rationale: str = "",
    operator: str = "USER",
    timestamp: str | None = None,
) -> Path:
    """Append an immutable veto/release event; this is never an approval action."""
    target = Path(path)
    payload = load_veto_ledger(target)
    normalized_symbol = symbol.strip().upper()
    normalized_action = action.strip().upper()
    if not normalized_symbol:
        raise ValueError("veto symbol is required")
    if normalized_action not in {"VETO", "RELEASE"}:
        raise ValueError("veto action must be VETO or RELEASE")
    events = list(payload["events"])
    events.append(
        {
            "event_id": f"{STRATEGY_ID}:{normalized_symbol}:{len(events) + 1}",
            "strategy_id": STRATEGY_ID,
            "symbol": normalized_symbol,
            "action": normalized_action,
            "timestamp": timestamp or _utc_now(),
            "rationale": rationale.strip() or None,
            "operator": operator.strip() or "USER",
        }
    )
    updated = dict(payload)
    updated["events"] = events
    return _atomic_json(target, updated)


def apply_active_vetoes_to_runtime_candidates(
    *,
    root: str | Path | None = None,
    ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    """Block current-cycle progression without mutating durable candidate state.

    For an actively vetoed symbol the runtime-only leveraged eligibility is set to
    false. Durable mapping/lifecycle state remains intact and can resume after a
    RELEASE event. No veto file means normal autonomous paper evaluation.
    """
    base = Path(root) if root is not None else Path.cwd()
    ledger = Path(ledger_path) if ledger_path is not None else base / DEFAULT_LEDGER_PATH
    runtime = base / DEFAULT_RUNTIME_CANDIDATES
    report_path = base / DEFAULT_VETO_REPORT
    payload = load_veto_ledger(ledger)
    active = active_vetoes(payload)
    blocked: list[str] = []

    if runtime.is_file() and active:
        with runtime.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        if "leveraged_vehicle_exists" not in fieldnames:
            raise ValueError("runtime candidate file missing leveraged_vehicle_exists")
        for row in rows:
            underlying = str(row.get("underlying_symbol", "")).strip().upper()
            leveraged = str(row.get("leveraged_symbol", "")).strip().upper()
            if underlying in active or leveraged in active:
                row["leveraged_vehicle_exists"] = "false"
                blocked.append(underlying)
        fd, temp_name = tempfile.mkstemp(prefix=f".{runtime.name}.", suffix=".tmp", dir=runtime.parent)
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, runtime)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    report = {
        "schema_version": "1.0",
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "approval_required": False,
        "absence_of_veto_allows_normal_progression": True,
        "active_veto_count": len(active),
        "active_veto_symbols": sorted(active),
        "runtime_blocked_candidates": sorted(set(blocked)),
        "broker_execution_allowed": False,
        "order_placement_allowed": False,
        "capital_movement_allowed": False,
    }
    _atomic_json(report_path, report)
    return report


def symbol_is_vetoed(symbol: str, *, ledger_path: str | Path) -> bool:
    target = symbol.strip().upper()
    return target in active_vetoes(load_veto_ledger(ledger_path))

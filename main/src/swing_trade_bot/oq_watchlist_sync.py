"""Synchronize Tuesday Opportunity Quality selections into Swing lifecycle state.

This module does not write watchlist_report.json and never creates positions. It
updates only durable candidate lifecycle state so the existing daily DiscoveryEngine
can continue to own watchlist reporting, Entry Score/timing, and later paper-only
progression. Active user vetoes block progression but do not erase durable state.

A verified underlying-to-leveraged-vehicle mapping is persistent strategy memory.
A candidate that previously left the active watchlist may therefore be selected by
the weekly mapped-universe Opportunity Quality review and promoted back to WATCHLIST.
That promotion is watchlist attention only: it never creates a position, bypasses
Entry Score, or authorizes broker execution.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .discovery_engine import CandidateState
from .enterprise_candidate_state import load_candidate_state, persist_candidate_state
from .leveraged_vehicle_registry import preferred_vehicle_mapping
from .user_veto_control import DEFAULT_LEDGER_PATH, active_vetoes, load_veto_ledger

STRATEGY_ID = "SWING-001"
SCHEMA_VERSION = "1.0"
DEFAULT_REVIEW_PATH = Path("results/weekly_mapped_universe_review.json")
DEFAULT_REPORT_PATH = Path("results/oq_watchlist_sync.json")
PRESERVE_STATUSES = {"WATCHLIST", "LOW", "MEDIUM", "HIGH"}
PROMOTABLE_STATUSES = {"DISCOVERY", "MONITOR", "REMOVED"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_review(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("weekly mapped universe review root must be an object")
    if payload.get("strategy_id") != STRATEGY_ID:
        raise ValueError("weekly mapped universe review strategy_id must be SWING-001")
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("weekly mapped universe review must be paper-only")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("weekly mapped universe review rows must be a list")
    return payload


def synchronize_oq_watchlist_state(
    *,
    root: str | Path | None = None,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    review_path: str | Path = DEFAULT_REVIEW_PATH,
    veto_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    """Apply OQ selection to durable candidate lifecycle without execution.

    Selected DISCOVERY/MONITOR/REMOVED names become WATCHLIST when the verified
    persistent mapping still exists. Existing WATCHLIST/LOW/MEDIUM/HIGH states are
    preserved. Non-selected names are never promoted or forcibly demoted by this
    bridge. Active user vetoes always block progression without erasing mapping or
    candidate state.
    """
    base = Path(root) if root is not None else Path.cwd()
    review = _load_review(base / Path(review_path))
    mapping = preferred_vehicle_mapping(base / Path(registry_path))
    ledger_path = Path(veto_ledger_path) if veto_ledger_path is not None else base / DEFAULT_LEDGER_PATH
    vetoed = set(active_vetoes(load_veto_ledger(ledger_path)))

    selected_rows = {
        str(row.get("underlying_symbol", "")).strip().upper(): row
        for row in review["rows"]
        if isinstance(row, Mapping) and row.get("selected_for_watchlist") is True
    }
    candidates, metadata = load_candidate_state(root=base)
    by_symbol = {candidate.underlying_symbol.upper(): candidate for candidate in candidates}
    updated = list(candidates)
    index = {candidate.underlying_symbol.upper(): i for i, candidate in enumerate(updated)}

    promoted: list[str] = []
    reactivated: list[str] = []
    retained: list[str] = []
    added: list[str] = []
    veto_blocked: list[str] = []
    removed_preserved: list[str] = []

    for symbol in sorted(selected_rows):
        vehicle = mapping.get(symbol)
        if not vehicle:
            raise ValueError(f"Selected OQ underlying has no verified preferred vehicle: {symbol}")
        is_vetoed = symbol in vetoed or vehicle in vetoed
        existing = by_symbol.get(symbol)
        if is_vetoed:
            veto_blocked.append(symbol)
            metadata.setdefault(symbol, {})["lifecycle_reason"] = "USER_VETO_ACTIVE_OQ_PROMOTION_BLOCKED"
            continue

        if existing is None:
            candidate = CandidateState(
                underlying_symbol=symbol,
                leveraged_symbol=vehicle,
                status="WATCHLIST",
            )
            updated.append(candidate)
            index[symbol] = len(updated) - 1
            by_symbol[symbol] = candidate
            added.append(symbol)
            metadata.setdefault(symbol, {})["lifecycle_reason"] = "OQ_V1_2_SELECTED_NEW_WATCHLIST"
            continue

        status = existing.status.upper()
        if status in PRESERVE_STATUSES:
            retained.append(symbol)
            metadata.setdefault(symbol, {})["lifecycle_reason"] = "OQ_V1_2_SELECTED_EXISTING_STATE_PRESERVED"
            continue
        if status in PROMOTABLE_STATUSES:
            promoted_candidate = replace(
                existing,
                leveraged_symbol=vehicle,
                status="WATCHLIST",
                days_in_status=0,
                leveraged_vehicle_exists=True,
            )
            updated[index[symbol]] = promoted_candidate
            by_symbol[symbol] = promoted_candidate
            promoted.append(symbol)
            if status == "REMOVED":
                reactivated.append(symbol)
                metadata.setdefault(symbol, {})["lifecycle_reason"] = "OQ_V1_2_SELECTED_REACTIVATED_WATCHLIST"
            else:
                metadata.setdefault(symbol, {})["lifecycle_reason"] = "OQ_V1_2_SELECTED_FOR_WATCHLIST"
            continue
        raise ValueError(f"Unsupported candidate lifecycle status for {symbol}: {existing.status}")

    persist_candidate_state(updated, metadata=metadata, root=base)
    selected = sorted(selected_rows)
    report = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "position_creation_allowed": False,
        "entry_score_bypassed": False,
        "generated_at_utc": _utc_now(),
        "authority": "FROZEN_OPPORTUNITY_QUALITY_V1_2_SELECTION_TO_DURABLE_SWING_LIFECYCLE",
        "persistent_mapping_requalification_enabled": True,
        "selected_underlyings": selected,
        "promoted_to_watchlist": promoted,
        "reactivated_to_watchlist": reactivated,
        "retained_existing_lifecycle": retained,
        "added_to_watchlist": added,
        "veto_blocked": veto_blocked,
        "removed_state_preserved": removed_preserved,
        "nonselected_state_preserved": True,
    }
    return report


def write_oq_watchlist_sync_report(payload: Mapping[str, Any], *, root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else Path.cwd()
    path = base / DEFAULT_REPORT_PATH
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


def synchronize_and_write_oq_watchlist_state(**kwargs: Any) -> dict[str, Any]:
    payload = synchronize_oq_watchlist_state(**kwargs)
    write_oq_watchlist_sync_report(payload, root=kwargs.get("root"))
    return payload


if __name__ == "__main__":
    result = synchronize_and_write_oq_watchlist_state()
    print(
        "OQ watchlist sync: "
        f"{len(result['selected_underlyings'])} selected; "
        f"{len(result['promoted_to_watchlist']) + len(result['added_to_watchlist'])} advanced; "
        f"{len(result['veto_blocked'])} veto blocked"
    )

"""Synchronize successful DiscoveryEngine results into durable Swing candidate state."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from .enterprise_candidate_state import load_candidate_state, persist_candidate_state

DEFAULT_WATCHLIST_REPORT = Path("results/watchlist_report.json")


def _number(row: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def sync_candidate_state_from_watchlist(
    *,
    root: str | Path | None = None,
    report_path: str | Path | None = None,
) -> Path:
    """Persist lifecycle output only after a successful Swing daily cycle."""
    base = Path(root) if root is not None else Path.cwd()
    source = Path(report_path) if report_path is not None else base / DEFAULT_WATCHLIST_REPORT
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("watchlist report rows must be a list")
    by_symbol = {
        str(row.get("underlying_symbol", "")).strip().upper(): row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("underlying_symbol", "")).strip()
    }
    candidates, metadata = load_candidate_state(root=base)
    updated = []
    for candidate in candidates:
        result = by_symbol.get(candidate.underlying_symbol.upper())
        if result is None:
            updated.append(candidate)
            continue
        next_status = str(result.get("watchlist_status", candidate.status)).strip().upper()
        allowed = {"DISCOVERY", "MONITOR", "WATCHLIST", "LOW", "MEDIUM", "HIGH", "REMOVED"}
        if next_status not in allowed:
            raise ValueError(f"Unsupported watchlist lifecycle status {next_status}")
        status_changed = next_status != candidate.status
        themes = tuple(item for item in str(result.get("themes", "")).split(";") if item) or candidate.themes
        updated.append(
            replace(
                candidate,
                status=next_status,
                paper_return=_number(result, "paper_return", candidate.paper_return),
                win_rate=_number(result, "win_rate", candidate.win_rate),
                profit_factor=_number(result, "profit_factor", candidate.profit_factor),
                trading_days=max(candidate.trading_days, int(_number(result, "trading_days", float(candidate.trading_days)))),
                days_in_status=0 if status_changed else candidate.days_in_status + 1,
                themes=themes,
            )
        )
        if status_changed:
            metadata.setdefault(candidate.underlying_symbol.upper(), {})["lifecycle_reason"] = "DISCOVERY_ENGINE_EVALUATION"
    return persist_candidate_state(updated, metadata=metadata, root=base)

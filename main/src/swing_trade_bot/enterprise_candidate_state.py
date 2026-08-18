"""Durable Swing-owned lifecycle state for Enterprise-imported discovery candidates.

The AI CIO nominates; Swing owns lifecycle state after intake. This store is seeded
from the historical example candidate file only when no durable state exists.
Subsequent runs read/write results/discovery_candidate_state.csv atomically.
"""
from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

from .discovery_engine import CandidateState, WatchlistRow, load_candidates

DEFAULT_SEED_PATH = Path("examples/discovery_candidates.csv")
DEFAULT_STATE_PATH = Path("results/discovery_candidate_state.csv")
STATE_EXTRA_FIELDS = (
    "first_enterprise_discovered_on",
    "last_enterprise_nominated_on",
    "lifecycle_reason",
)


def _atomic_write(path: Path, candidates: Sequence[CandidateState], metadata: Mapping[str, Mapping[str, str]] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    fields = [*CandidateState.__dataclass_fields__, *STATE_EXTRA_FIELDS]
    metadata = metadata or {}
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for candidate in candidates:
                row = asdict(candidate)
                row["themes"] = ";".join(candidate.themes)
                row.update({field: metadata.get(candidate.underlying_symbol.upper(), {}).get(field, "") for field in STATE_EXTRA_FIELDS})
                writer.writerow(row)
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


def read_state_metadata(path: str | Path) -> dict[str, dict[str, str]]:
    source = Path(path)
    if not source.is_file():
        return {}
    result: dict[str, dict[str, str]] = {}
    with source.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("underlying_symbol", "")).strip().upper()
            if not symbol:
                continue
            result[symbol] = {field: str(row.get(field, "") or "") for field in STATE_EXTRA_FIELDS}
    return result


def ensure_candidate_state(*, root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else Path.cwd()
    state_path = base / DEFAULT_STATE_PATH
    if state_path.is_file():
        return state_path
    seed_path = base / DEFAULT_SEED_PATH
    if not seed_path.is_file():
        raise FileNotFoundError(f"Candidate seed missing: {seed_path}")
    _atomic_write(state_path, load_candidates(seed_path))
    return state_path


def load_candidate_state(*, root: str | Path | None = None) -> tuple[list[CandidateState], dict[str, dict[str, str]]]:
    state_path = ensure_candidate_state(root=root)
    return load_candidates(state_path), read_state_metadata(state_path)


def persist_candidate_state(
    candidates: Sequence[CandidateState],
    *,
    metadata: Mapping[str, Mapping[str, str]] | None = None,
    root: str | Path | None = None,
) -> Path:
    base = Path(root) if root is not None else Path.cwd()
    return _atomic_write(base / DEFAULT_STATE_PATH, candidates, metadata)


def mark_enterprise_nomination(
    metadata: dict[str, dict[str, str]],
    symbol: str,
    *,
    nominated_on: date,
) -> None:
    key = symbol.strip().upper()
    row = metadata.setdefault(key, {})
    row.setdefault("first_enterprise_discovered_on", nominated_on.isoformat())
    if not row.get("first_enterprise_discovered_on"):
        row["first_enterprise_discovered_on"] = nominated_on.isoformat()
    row["last_enterprise_nominated_on"] = nominated_on.isoformat()


def update_state_from_watchlist(
    rows: Sequence[WatchlistRow],
    *,
    root: str | Path | None = None,
) -> Path:
    """Persist legitimate DiscoveryEngine lifecycle results after a successful cycle."""
    candidates, metadata = load_candidate_state(root=root)
    by_symbol = {row.underlying_symbol.upper(): row for row in rows}
    updated: list[CandidateState] = []
    for candidate in candidates:
        result = by_symbol.get(candidate.underlying_symbol.upper())
        if result is None:
            updated.append(candidate)
            continue
        status_changed = result.watchlist_status != candidate.status
        next_days = 0 if status_changed else candidate.days_in_status + 1
        updated.append(
            replace(
                candidate,
                status=result.watchlist_status,
                paper_return=result.paper_return,
                win_rate=result.win_rate,
                profit_factor=result.profit_factor,
                trading_days=max(candidate.trading_days, result.trading_days),
                days_in_status=next_days,
                themes=tuple(item for item in result.themes.split(";") if item),
            )
        )
        if status_changed:
            metadata.setdefault(candidate.underlying_symbol.upper(), {})["lifecycle_reason"] = "DISCOVERY_ENGINE_EVALUATION"
    return persist_candidate_state(updated, metadata=metadata, root=root)

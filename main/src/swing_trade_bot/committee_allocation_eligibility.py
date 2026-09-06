"""Fail-closed allocation eligibility from frozen Swing committee evidence.

This module does not score opportunities, invent Entry Score, rank securities, or
allocate capital. It mirrors the frozen Opportunity/Entry committee boundaries so
portfolio allocation can consume an explicit current-cycle eligibility artifact
for every active ranked watchlist candidate rather than inferring eligibility from
confidence or watchlist status.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

PAPER_TRADE_MODE = True
OPPORTUNITY_MINIMUM = 70.0
ENTRY_MINIMUM = 70.0
DEFAULT_OUTPUT_PATH = Path("results/committee_allocation_eligibility.json")


def build_committee_allocation_eligibility(
    results_dir: str | Path,
    *,
    paper_trade_mode: bool = True,
) -> dict[str, Any]:
    if not paper_trade_mode:
        raise ValueError("Committee allocation eligibility requires paper_trade_mode=True")
    root = Path(results_dir)
    watchlist_path = root / "watchlist_report.json"
    quality_path = root / "opportunity_quality_report.json"
    inputs_path = root / "opportunity_quality_inputs.json"
    if not watchlist_path.is_file():
        raise FileNotFoundError(watchlist_path)
    if not quality_path.is_file():
        raise FileNotFoundError(quality_path)

    watchlist = _rows(_load(watchlist_path))
    quality = _rows(_load(quality_path))
    inputs = _rows(_load(inputs_path)) if inputs_path.is_file() else []
    rows: list[dict[str, Any]] = []

    for candidate in watchlist:
        if not _active(candidate):
            continue
        underlying = _text(candidate, "underlying_symbol", "symbol", "ticker").upper()
        leveraged = _text(candidate, "leveraged_symbol").upper()
        if not underlying and not leveraged:
            continue
        key = underlying or leveraged
        quality_row = _find(quality, underlying, leveraged)
        input_row = _find(inputs, underlying, leveraged)
        opportunity = _number(quality_row, "opportunity_quality_score", "opportunity_quality", "final_score")
        entry = _number(quality_row, "entry_score")
        if entry is None:
            entry = _number(input_row, "entry_score")
        thesis = _bool(quality_row, "thesis_intact")
        if thesis is None:
            thesis = _bool(input_row, "thesis_intact")

        opportunity_pass = opportunity is not None and opportunity >= OPPORTUNITY_MINIMUM
        entry_pass = opportunity_pass and entry is not None and thesis is True and entry >= ENTRY_MINIMUM
        eligible = opportunity_pass and entry_pass
        if not opportunity_pass:
            status = "REJECTED" if opportunity is not None else "WAIT"
            reason = "OPPORTUNITY_THRESHOLD_NOT_MET" if opportunity is not None else "OPPORTUNITY_EVIDENCE_PENDING"
        elif entry is None or thesis is None:
            status, reason = "WAIT", "ENTRY_EVIDENCE_PENDING"
        elif not entry_pass:
            status, reason = "REJECTED", "ENTRY_THRESHOLD_NOT_MET"
        else:
            status, reason = "ELIGIBLE_FOR_ALLOCATION", "RANKED_ALLOCATION_ELIGIBLE"

        rows.append({
            "symbol": key,
            "underlying_symbol": underlying,
            "leveraged_symbol": leveraged,
            "opportunity_quality_score": opportunity,
            "opportunity_minimum": OPPORTUNITY_MINIMUM,
            "entry_score": entry,
            "entry_minimum": ENTRY_MINIMUM,
            "thesis_intact": thesis,
            "eligible_for_allocation": eligible,
            "final_status": status,
            "reason_code": reason,
        })

    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "advisory_only": True,
        "broker_execution_enabled": False,
        "capital_movement_enabled": False,
        "eligibility_rule": "OPPORTUNITY_QUALITY_GTE_70_AND_ENTRY_SCORE_GTE_70_AND_THESIS_INTACT",
        "rows": rows,
        "eligible_symbols": sorted(row["symbol"] for row in rows if row["eligible_for_allocation"]),
    }


def build_and_write_committee_allocation_eligibility(
    results_dir: str | Path,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    *,
    paper_trade_mode: bool = True,
) -> dict[str, Any]:
    payload = build_committee_allocation_eligibility(results_dir, paper_trade_mode=paper_trade_mode)
    _atomic_json(Path(output_path), payload)
    return payload


def load_eligible_symbols(path: str | Path) -> set[str]:
    payload = _load(Path(path))
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("eligibility artifact must be paper_trade_mode=true")
    values = payload.get("eligible_symbols")
    if not isinstance(values, list):
        raise ValueError("eligibility artifact must contain eligible_symbols list")
    return {str(value).strip().upper() for value in values if str(value).strip()}


def _active(row: Mapping[str, Any]) -> bool:
    return _text(row, "capacity_status", default="ACTIVE").upper() == "ACTIVE" and _text(row, "watchlist_status", default="WATCHLIST").upper() != "REMOVED"


def _find(rows: Sequence[Mapping[str, Any]], *symbols: str) -> Mapping[str, Any]:
    wanted = {symbol.upper() for symbol in symbols if symbol}
    for row in rows:
        values = {_text(row, "symbol").upper(), _text(row, "ticker").upper(), _text(row, "underlying_symbol").upper(), _text(row, "leveraged_symbol").upper()} - {""}
        if values & wanted:
            return row
    return {}


def _rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = payload.get("rows")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, Mapping)]


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _value(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _text(row: Mapping[str, Any], *names: str, default: str = "") -> str:
    value = _value(row, *names)
    return default if value is None else str(value).strip()


def _number(row: Mapping[str, Any], *names: str) -> float | None:
    value = _value(row, *names)
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace("%", "").replace(",", ""))
    except ValueError:
        return None


def _bool(row: Mapping[str, Any], *names: str) -> bool | None:
    value = _value(row, *names)
    if isinstance(value, bool):
        return value
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "intact"}:
        return True
    if text in {"false", "0", "no", "broken"}:
        return False
    return None


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, allow_nan=False, sort_keys=True)
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

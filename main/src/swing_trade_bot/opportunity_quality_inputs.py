"""Assemble frozen Opportunity Quality inputs from existing paper-only evidence.

Candidate selection is owned by the current ranked watchlist. Opportunity Quality
inputs must not depend on committee runtime evidence because committees consume
the resulting Opportunity Quality report later in the same cycle.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

COMPONENTS = (
    "fundamental_analysis_score",
    "market_intelligence_score",
    "conviction_score",
    "momentum_score",
    "technical_analysis_score",
    "market_regime_support_score",
    "portfolio_risk_adjustment_score",
    "entry_score",
)
SOURCES = (
    "watchlist_report.json",
    "fundamental_analysis.json",
    "market_intelligence.json",
    "confidence_report.json",
    "confidence_report.csv",
    "momentum_scores.json",
    "technical_analysis.json",
    "market_regime.json",
    "portfolio_risk_report.json",
    "entry_score_report.json",
)


def build_opportunity_quality_inputs(results_dir: str | Path, *, paper_trade_mode: bool = True) -> dict[str, Any]:
    if not paper_trade_mode:
        raise ValueError("Opportunity Quality inputs require paper_trade_mode=True")
    root = Path(results_dir)
    symbol, underlying, leveraged = _selected_watchlist_context(root)
    aliases = {symbol, underlying, leveraged} - {""}

    rows: list[tuple[str, Mapping[str, Any]]] = []
    available: list[str] = []
    for name in SOURCES:
        path = root / name
        if not path.is_file():
            continue
        available.append(f"results/{name}")
        for row in _read_rows(path):
            if _symbol(row) in aliases:
                rows.append((name, row))

    output: dict[str, Any] = {"symbol": symbol}
    provenance: dict[str, str | None] = {}
    for component in COMPONENTS:
        value = None
        source = None
        for name, row in rows:
            candidates = (component,)
            if component == "fundamental_analysis_score" and name == "watchlist_report.json":
                candidates = (component, "financial_health_score")
            found = _number(row, *candidates)
            if found is not None:
                value, source = found, f"results/{name}"
                break
        output[component] = value
        provenance[component] = source

    thesis_intact = None
    thesis_source = None
    for name, row in rows:
        found = _optional_bool(row, "thesis_intact")
        if found is not None:
            thesis_intact, thesis_source = found, f"results/{name}"
            break
    output["thesis_intact"] = thesis_intact
    provenance["thesis_intact"] = thesis_source

    return {
        "paper_trade_mode": True,
        "missing_evidence_rule": "missing evidence = 0",
        "entry_score_display_only": True,
        "selected_by": "highest evidence rank",
        "selection_source": "results/watchlist_report.json",
        "selected_underlying_symbol": underlying,
        "selected_leveraged_symbol": leveraged,
        "source_artifacts": sorted(set(available)),
        "component_provenance": provenance,
        "rows": [output],
    }


def write_opportunity_quality_inputs(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    if payload.get("paper_trade_mode") is not True or payload.get("entry_score_display_only") is not True:
        raise ValueError("Unsafe Opportunity Quality input payload")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, allow_nan=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_and_write_opportunity_quality_inputs(results_dir: str | Path, output_path: str | Path | None = None) -> Path:
    root = Path(results_dir)
    return write_opportunity_quality_inputs(build_opportunity_quality_inputs(root), output_path or root / "opportunity_quality_inputs.json")


def _selected_watchlist_context(root: Path) -> tuple[str, str, str]:
    watchlist_path = root / "watchlist_report.json"
    if not watchlist_path.is_file():
        raise FileNotFoundError(f"Ranked watchlist is missing: {watchlist_path}")
    candidates = [row for row in _read_rows(watchlist_path) if _candidate_is_active(row)]
    if not candidates:
        raise ValueError("Ranked watchlist contains no active candidates")
    selected = min(candidates, key=_rank_key)
    underlying = _text(selected, "underlying_symbol", "symbol", "ticker").upper()
    leveraged = _text(selected, "leveraged_symbol").upper()
    symbol = underlying or leveraged
    if not symbol:
        raise ValueError("Highest-ranked watchlist candidate has no symbol")
    return symbol, underlying, leveraged


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> list[Mapping[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    payload = _json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("rows", "scores", "results", "candidates", "allocations"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        return [payload]
    return []


def _symbol(row: Mapping[str, Any]) -> str:
    for key in ("symbol", "underlying_symbol", "leveraged_symbol", "ticker"):
        if row.get(key):
            return str(row[key]).strip().upper()
    return ""


def _candidate_is_active(row: Mapping[str, Any]) -> bool:
    capacity = _text(row, "capacity_status", default="ACTIVE").upper()
    status = _text(row, "watchlist_status", default="WATCHLIST").upper()
    return capacity == "ACTIVE" and status != "REMOVED"


def _rank_key(row: Mapping[str, Any]) -> tuple[int, int, float, str]:
    high = _optional_int(row, "high_priority_rank")
    standard = _optional_int(row, "watchlist_rank")
    if high is not None:
        tier, rank = 0, high
    elif standard is not None:
        tier, rank = 1, standard
    else:
        tier, rank = 2, 999999
    composite = _number(row, "composite_score") or 0.0
    return tier, rank, -composite, _text(row, "underlying_symbol", "symbol")


def _value(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _text(row: Mapping[str, Any], *names: str, default: str = "") -> str:
    value = _value(row, *names)
    return default if value is None else str(value).strip()


def _optional_int(row: Mapping[str, Any], *names: str) -> int | None:
    value = _number(row, *names)
    return None if value is None else int(value)


def _optional_bool(row: Mapping[str, Any], *names: str) -> bool | None:
    value = _value(row, *names)
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "intact"}:
        return True
    if text in {"false", "0", "no", "broken"}:
        return False
    return None


def _number(row: Mapping[str, Any], *names: str) -> float | None:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is None or str(value).strip() == "":
            continue
        try:
            number = float(str(value).replace("%", "").replace(",", ""))
        except ValueError:
            continue
        if math.isfinite(number) and 0 <= number <= 100:
            return number
    return None

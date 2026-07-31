"""Assemble frozen Opportunity Quality inputs from existing paper-only evidence."""
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
    evidence_path = root / "swing_committee_runtime_evidence.json"
    if not evidence_path.is_file():
        raise FileNotFoundError(f"Runtime evidence is missing: {evidence_path}")
    evidence = _json(evidence_path)
    symbol = str(evidence.get("symbol") or evidence.get("underlying_symbol") or "").upper()
    aliases = {symbol, str(evidence.get("underlying_symbol") or "").upper(), str(evidence.get("leveraged_symbol") or "").upper()} - {""}
    if not symbol:
        raise ValueError("Runtime evidence has no selected symbol")
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
    return {
        "paper_trade_mode": True,
        "missing_evidence_rule": "missing evidence = 0",
        "entry_score_display_only": True,
        "selected_by": "highest evidence rank",
        "source_artifacts": sorted(set(available + ["results/swing_committee_runtime_evidence.json"])),
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

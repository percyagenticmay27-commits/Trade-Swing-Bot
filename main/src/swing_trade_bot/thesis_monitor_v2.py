"""Dynamic paper-only thesis monitor for the modern Swing Bot architecture.

Version 2.0 derives thesis health from current authoritative Swing evidence rather
than handwritten symbol fixtures.  It does not use Entry Score, historical
backtest performance, Shadow performance, broker state, or live execution.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

VERSION = "2.0.0"
SCHEMA_VERSION = "2.0"
STRATEGY_ID = "SWING-001"

COMPONENT_WEIGHTS: dict[str, float] = {
    "fundamental_analysis_score": 0.25,
    "market_intelligence_score": 0.20,
    "conviction_score": 0.20,
    "momentum_score": 0.10,
    "technical_analysis_score": 0.10,
    "market_regime_support_score": 0.10,
    "portfolio_risk_adjustment_score": 0.05,
}

STRONG_THRESHOLD = 85.0
INTACT_THRESHOLD = 70.0
WEAKENING_THRESHOLD = 55.0
MINIMUM_EVIDENCE_COUNT = 5
WEAK_COMPONENT_THRESHOLD = 55.0
MATERIAL_HEALTH_DECLINE = -12.0


@dataclass(frozen=True, slots=True)
class ThesisV2Review:
    underlying_symbol: str
    vehicle_symbol: str | None
    primary_strategy_id: str | None
    thesis_state: str
    thesis_health_score: float | None
    thesis_intact: bool | None
    evidence_status: str
    evidence_count: int
    weak_evidence_count: int
    opportunity_quality_score: float | None
    opportunity_quality_change: float | None
    thesis_health_change: float | None
    strongest_components: tuple[str, ...]
    weakest_components: tuple[str, ...]
    dynamic_summary: str
    component_evidence: Mapping[str, Mapping[str, Any]]
    reason: str

    def row(self) -> dict[str, Any]:
        return asdict(self)


def build_thesis_monitor_v2(
    *,
    results_dir: str | Path,
    assignments_path: str | Path | None = None,
    paper_trade_mode: bool = True,
) -> dict[str, Any]:
    if not paper_trade_mode:
        raise ValueError("Thesis Monitor V2 requires paper_trade_mode=True")

    results = Path(results_dir)
    oq_inputs_path = results / "opportunity_quality_inputs.json"
    oq_report_path = results / "opportunity_quality_report.json"
    watchlist_path = results / "watchlist_report.json"
    if not oq_inputs_path.is_file():
        raise FileNotFoundError(f"Missing current Opportunity Quality inputs: {oq_inputs_path}")
    if not oq_report_path.is_file():
        raise FileNotFoundError(f"Missing current Opportunity Quality report: {oq_report_path}")
    if not watchlist_path.is_file():
        raise FileNotFoundError(f"Missing current watchlist: {watchlist_path}")

    oq_inputs = _json(oq_inputs_path)
    oq_report = _json(oq_report_path)
    watchlist = _json(watchlist_path)
    assignment_file = Path(assignments_path) if assignments_path else results.parent / "configs" / "frozen_strategy_assignments.json"
    assignments = _json(assignment_file) if assignment_file.is_file() else {}

    previous_path = results / "thesis_monitor_v2_report.json"
    previous = _json(previous_path) if previous_path.is_file() else {}
    previous_rows = {_symbol(row): row for row in _rows(previous, "reviews") if _symbol(row)}

    input_rows = {_symbol(row): row for row in _rows(oq_inputs, "rows") if _symbol(row)}
    quality_rows = {_symbol(row): row for row in _rows(oq_report, "rows") if _symbol(row)}
    provenance = oq_inputs.get("component_provenance_by_symbol", {}) if isinstance(oq_inputs, Mapping) else {}
    mappings = _strategy_mappings(assignments)

    reviews: list[ThesisV2Review] = []
    for item in _active_watchlist_rows(watchlist):
        underlying = _text(item, "underlying_symbol", "symbol", "ticker").upper()
        vehicle = _text(item, "leveraged_symbol").upper() or None
        if not underlying:
            continue
        mapping = mappings.get(underlying)
        if mapping:
            vehicle = mapping.get("vehicle_symbol") or vehicle
        source = input_rows.get(underlying, {})
        quality = quality_rows.get(underlying, {})
        prior = previous_rows.get(underlying, {})
        review = _review_one(
            underlying=underlying,
            vehicle=vehicle,
            primary_strategy_id=(mapping or {}).get("primary_strategy_id"),
            source=source,
            quality=quality,
            provenance=provenance.get(underlying, {}) if isinstance(provenance, Mapping) else {},
            previous=prior,
        )
        reviews.append(review)

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": VERSION,
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "dynamic_universe": True,
        "dynamic_evidence": True,
        "handwritten_symbol_theses_used": False,
        "entry_score_used_in_thesis_health": False,
        "historical_backtest_used_in_thesis_health": False,
        "shadow_performance_used_in_thesis_health": False,
        "component_weights": COMPONENT_WEIGHTS,
        "thresholds": {
            "strong": STRONG_THRESHOLD,
            "intact": INTACT_THRESHOLD,
            "weakening": WEAKENING_THRESHOLD,
            "minimum_evidence_count": MINIMUM_EVIDENCE_COUNT,
            "weak_component_threshold": WEAK_COMPONENT_THRESHOLD,
            "material_health_decline": MATERIAL_HEALTH_DECLINE,
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reviews": [review.row() for review in reviews],
    }


def write_thesis_monitor_v2(payload: Mapping[str, Any], results_dir: str | Path) -> tuple[Path, Path]:
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("Unsafe Thesis Monitor V2 payload")
    results = Path(results_dir)
    results.mkdir(parents=True, exist_ok=True)
    json_path = results / "thesis_monitor_v2_report.json"
    md_path = results / "thesis_monitor_v2_report.md"
    json_path.write_text(json.dumps(dict(payload), indent=2, allow_nan=False, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(payload) + "\n", encoding="utf-8")
    return json_path, md_path


def build_and_write_thesis_monitor_v2(*, results_dir: str | Path, assignments_path: str | Path | None = None) -> dict[str, Any]:
    payload = build_thesis_monitor_v2(results_dir=results_dir, assignments_path=assignments_path)
    write_thesis_monitor_v2(payload, results_dir)
    return payload


def _review_one(*, underlying: str, vehicle: str | None, primary_strategy_id: str | None, source: Mapping[str, Any], quality: Mapping[str, Any], provenance: Mapping[str, Any], previous: Mapping[str, Any]) -> ThesisV2Review:
    component_evidence: dict[str, dict[str, Any]] = {}
    values: dict[str, float] = {}
    for name, weight in COMPONENT_WEIGHTS.items():
        value = _optional_score(source.get(name))
        component_evidence[name] = {
            "score": value,
            "weight": weight,
            "source": provenance.get(name) if isinstance(provenance, Mapping) else None,
        }
        if value is not None:
            values[name] = value

    evidence_count = len(values)
    weak_count = sum(1 for value in values.values() if value < WEAK_COMPONENT_THRESHOLD)
    oq_score = _optional_score(quality.get("opportunity_quality_score"))
    previous_health = _optional_score(previous.get("thesis_health_score"))
    previous_oq = _optional_score(previous.get("opportunity_quality_score"))

    if evidence_count < MINIMUM_EVIDENCE_COUNT:
        return ThesisV2Review(
            underlying, vehicle, primary_strategy_id, "unknown", None, None,
            "EVIDENCE_PENDING", evidence_count, weak_count, oq_score,
            _change(oq_score, previous_oq), None, (), (),
            _summary(values), component_evidence,
            "Insufficient current authoritative evidence for a thesis decision.",
        )

    total_weight = sum(COMPONENT_WEIGHTS[name] for name in values)
    health = sum(values[name] * COMPONENT_WEIGHTS[name] for name in values) / total_weight
    health = round(health, 6)
    health_change = _change(health, previous_health)
    oq_change = _change(oq_score, previous_oq)

    ranked = sorted(values.items(), key=lambda pair: (-pair[1], pair[0]))
    strongest = tuple(name for name, _ in ranked[:2])
    weakest = tuple(name for name, _ in sorted(values.items(), key=lambda pair: (pair[1], pair[0]))[:2])

    material_decline = health_change is not None and health_change <= MATERIAL_HEALTH_DECLINE
    if material_decline or weak_count >= 3:
        state = "broken" if health < WEAKENING_THRESHOLD else "weakening"
    elif health >= STRONG_THRESHOLD:
        state = "strong"
    elif health >= INTACT_THRESHOLD:
        state = "intact"
    elif health >= WEAKENING_THRESHOLD:
        state = "weakening"
    else:
        state = "broken"

    intact = state in {"strong", "intact"}
    reason = {
        "strong": "Current authoritative evidence supports a strong thesis.",
        "intact": "Current authoritative evidence supports an intact thesis.",
        "weakening": "Current evidence is weakening or has materially deteriorated.",
        "broken": "Current authoritative evidence does not support an intact thesis.",
    }[state]
    return ThesisV2Review(
        underlying, vehicle, primary_strategy_id, state, health, intact,
        "AVAILABLE", evidence_count, weak_count, oq_score, oq_change,
        health_change, strongest, weakest, _summary(values), component_evidence, reason,
    )


def _strategy_mappings(payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    strategies = payload.get("strategies", []) if isinstance(payload, Mapping) else []
    primaries: dict[str, dict[str, str]] = {}
    for row in strategies if isinstance(strategies, list) else []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("assignment_mode", "")).upper() != "DIRECT" or row.get("enabled") is False:
            continue
        signal = _text(row, "signal_symbol").upper()
        vehicle = _text(row, "vehicle_symbol").upper()
        strategy = _text(row, "strategy_id")
        if signal:
            primaries[signal] = {"vehicle_symbol": vehicle, "primary_strategy_id": strategy}
    return primaries


def _active_watchlist_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = _rows(payload, "rows")
    active = []
    for row in rows:
        capacity = _text(row, "capacity_status", default="ACTIVE").upper()
        status = _text(row, "watchlist_status", default="WATCHLIST").upper()
        if capacity == "ACTIVE" and status != "REMOVED":
            active.append(row)
    return active


def _summary(values: Mapping[str, float]) -> str:
    if not values:
        return "No current thesis components are available."
    strongest = max(values.items(), key=lambda pair: pair[1])
    weakest = min(values.items(), key=lambda pair: pair[1])
    return f"Strongest current component: {strongest[0]}={strongest[1]:.2f}; weakest: {weakest[0]}={weakest[1]:.2f}."


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Thesis Monitor V2 Report", "",
        "Paper-only. Dynamic current-universe thesis evidence. Entry Score is excluded.", "",
        "| Underlying | Vehicle | Primary Strategy | Thesis | Health | Intact | Evidence |",
        "|---|---|---|---|---:|---|---:|",
    ]
    for row in payload.get("reviews", []):
        score = row.get("thesis_health_score")
        score_text = "N/A" if score is None else f"{float(score):.2f}"
        lines.append(f"| {row.get('underlying_symbol')} | {row.get('vehicle_symbol') or ''} | {row.get('primary_strategy_id') or ''} | {row.get('thesis_state')} | {score_text} | {row.get('thesis_intact')} | {row.get('evidence_count')} |")
    return "\n".join(lines)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(payload: Any, key: str) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    return []


def _symbol(row: Mapping[str, Any]) -> str:
    return _text(row, "underlying_symbol", "symbol", "ticker").upper()


def _text(row: Mapping[str, Any], *names: str, default: str = "") -> str:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return str(value).strip()
    return default


def _optional_score(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    number = float(value)
    if number < 0 or number > 100:
        raise ValueError("Thesis component scores must be between 0 and 100")
    return number


def _change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 6)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dynamic paper-only Thesis Monitor V2")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--assignments", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    results = args.results_dir or root / "results"
    assignments = args.assignments or root / "configs" / "frozen_strategy_assignments.json"
    payload = build_and_write_thesis_monitor_v2(results_dir=results, assignments_path=assignments)
    print(json.dumps({
        "review_count": len(payload["reviews"]),
        "intact_symbols": [row["underlying_symbol"] for row in payload["reviews"] if row["thesis_intact"] is True],
        "pending_symbols": [row["underlying_symbol"] for row in payload["reviews"] if row["thesis_intact"] is None],
        "paper_trade_mode": True,
    }, indent=2))


if __name__ == "__main__":
    main()

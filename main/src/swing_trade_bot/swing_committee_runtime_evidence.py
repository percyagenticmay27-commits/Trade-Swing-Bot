"""Build authentic paper-only committee evidence for the highest-ranked candidate."""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_NAME = "swing_committee_runtime_evidence"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
COMMITTEES = (
    "DISCOVERY_COMMITTEE",
    "OPPORTUNITY_COMMITTEE",
    "ENTRY_COMMITTEE",
    "PORTFOLIO_COMMITTEE",
    "EXIT_COMMITTEE",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_runtime_evidence(
    results_dir: str | Path,
    *,
    generated_at_utc: str | None = None,
    paper_trade_mode: bool = True,
) -> dict[str, Any]:
    """Select the highest evidence-ranked candidate and build five committee steps.

    Missing downstream evidence is recorded as HOLD. Scores are never invented.
    """
    if not paper_trade_mode:
        raise ValueError("Committee runtime evidence requires paper_trade_mode=True")
    root = Path(results_dir)
    watchlist_path = root / "watchlist_report.json"
    if not watchlist_path.is_file():
        raise FileNotFoundError(f"Required ranked watchlist is missing: {watchlist_path}")
    watchlist_payload = _read_json(watchlist_path)
    candidates = [row for row in _rows(watchlist_payload) if _candidate_is_active(row)]
    if not candidates:
        raise ValueError("Ranked watchlist contains no active candidates")
    selected = min(candidates, key=_rank_key)
    underlying = _text(selected, "underlying_symbol", "symbol", "ticker").upper()
    leveraged = _text(selected, "leveraged_symbol").upper()
    symbol = underlying or leveraged
    if not symbol:
        raise ValueError("Highest-ranked watchlist candidate has no symbol")

    quality_path = root / "opportunity_quality_inputs.json"
    quality_row = _find_symbol(_optional_rows(quality_path), underlying, leveraged)
    allocation_path = root / "portfolio_allocations.json"
    allocation_row = _find_symbol(
        _rows(_read_json(allocation_path), keys=("allocations", "rows")) if allocation_path.is_file() else [],
        underlying,
        leveraged,
    )
    strategy_path = root / "strategy_recommendations.csv"
    strategy_row = _find_symbol(_read_csv(strategy_path) if strategy_path.is_file() else [], underlying, leveraged)
    lifecycle_path = root / "trade_lifecycle_report.json"
    lifecycle_row = _find_symbol(_optional_rows(lifecycle_path, keys=("reviews", "rows")), underlying, leveraged)

    strategy_id = _text(strategy_row, "active_strategy", "recommended_strategy", default="STRATEGY_A").upper().replace(" ", "_")
    sources = ["results/watchlist_report.json"]
    discovery_evidence = {
        "underlying_symbol": underlying,
        "leveraged_symbol": leveraged,
        "high_priority_rank": _optional_int(selected, "high_priority_rank"),
        "watchlist_rank": _optional_int(selected, "watchlist_rank"),
        "composite_score": _number(selected, "composite_score"),
        "source_confluence_score": _number(selected, "source_confluence_score"),
        "financial_health_score": _number(selected, "financial_health_score"),
        "capacity_status": _text(selected, "capacity_status"),
    }
    steps: list[dict[str, Any]] = [
        _step("DISCOVERY_COMMITTEE", 1, "PASS", ["HIGHEST_EVIDENCE_RANK"], discovery_evidence, sources)
    ]

    opportunity_score = _optional_number(quality_row, "opportunity_quality", "opportunity_quality_score", "final_score")
    if opportunity_score is None:
        opportunity_status = "HOLD"
        opportunity_reasons = ["OPPORTUNITY_EVIDENCE_PENDING"]
        opportunity_evidence: dict[str, Any] = {"score_available": False}
    else:
        opportunity_status = "PASS" if opportunity_score >= 70.0 else "FAIL"
        opportunity_reasons = ["OPPORTUNITY_THRESHOLD_MET" if opportunity_status == "PASS" else "OPPORTUNITY_THRESHOLD_NOT_MET"]
        opportunity_evidence = {"score_available": True, "opportunity_quality_score": opportunity_score, "minimum_score": 70.0}
        sources.append("results/opportunity_quality_inputs.json")
    steps.append(_step("OPPORTUNITY_COMMITTEE", 2, opportunity_status, opportunity_reasons, opportunity_evidence, sources))

    entry_score = _optional_number(quality_row, "entry_score")
    thesis_intact = _optional_bool(quality_row, "thesis_intact")
    if opportunity_status == "FAIL":
        entry_status, entry_reasons = "SKIPPED", ["OPPORTUNITY_REJECTED"]
    elif opportunity_status != "PASS" or entry_score is None or thesis_intact is None:
        entry_status, entry_reasons = "HOLD", ["ENTRY_EVIDENCE_PENDING"]
    else:
        entry_status = "PASS" if entry_score >= 70.0 and thesis_intact else "FAIL"
        entry_reasons = ["ENTRY_THRESHOLD_MET" if entry_status == "PASS" else "ENTRY_THRESHOLD_NOT_MET"]
    entry_evidence = {"entry_score": entry_score, "minimum_score": 70.0, "thesis_intact": thesis_intact}
    steps.append(_step("ENTRY_COMMITTEE", 3, entry_status, entry_reasons, entry_evidence, sources))

    allocation = _optional_number(allocation_row, "allocation_percent", "target_allocation")
    if entry_status == "FAIL" or opportunity_status == "FAIL":
        portfolio_status, portfolio_reasons = "SKIPPED", ["CANDIDATE_NOT_ENTRY_APPROVED"]
    elif entry_status != "PASS":
        portfolio_status, portfolio_reasons = "HOLD", ["ENTRY_APPROVAL_PENDING"]
    elif allocation is None or allocation <= 0:
        portfolio_status, portfolio_reasons = "HOLD", ["RANKED_ALLOCATION_PENDING"]
    else:
        portfolio_status, portfolio_reasons = "PASS", ["RANKED_PAPER_ALLOCATION_PRESENT"]
        sources.append("results/portfolio_allocations.json")
    portfolio_evidence = {
        "allocation_percent": allocation,
        "rank_controls_relative_allocation": True,
        "strategy_boost_applied": False,
        "theme_adjustment_applied": False,
        "historical_return_weighting_applied": False,
    }
    steps.append(_step("PORTFOLIO_COMMITTEE", 4, portfolio_status, portfolio_reasons, portfolio_evidence, sources))

    if lifecycle_row:
        exit_status = "REVIEW" if _text(lifecycle_row, "recommended_state", "status").lower() == "review_required" else "HOLD"
        exit_reasons = ["HELD_POSITION_REVIEWED"]
        exit_evidence = dict(lifecycle_row)
        sources.append("results/trade_lifecycle_report.json")
    else:
        exit_status, exit_reasons, exit_evidence = "NOT_APPLICABLE", ["NO_HELD_POSITION_EVIDENCE"], {}
    steps.append(_step("EXIT_COMMITTEE", 5, exit_status, exit_reasons, exit_evidence, sources))

    if portfolio_status == "PASS":
        final_status = "ALLOCATED"
    elif opportunity_status == "FAIL" or entry_status == "FAIL":
        final_status = "REJECTED"
    else:
        final_status = "WAIT"
    generated_at = generated_at_utc or _utc_now()
    return {
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "evaluation_cycle_id": f"SWING-{generated_at.replace(':', '').replace('-', '')}",
        "symbol": symbol,
        "underlying_symbol": underlying,
        "leveraged_symbol": leveraged,
        "strategy_id": strategy_id,
        "committee_steps": steps,
        "final_status": final_status,
        "source_artifacts": sorted(set(sources)),
        "bias_audit": {
            "sector_bias_applied": False,
            "theme_bias_applied": False,
            "concentration_limit_applied": False,
            "stock_history_bias_applied": False,
            "market_regime_veto_applied": False,
        },
        "generated_at_utc": generated_at,
        "paper_trade_mode": True,
        "advisory_only": True,
        "broker_execution_allowed": False,
        "capital_movement_allowed": False,
    }


def write_runtime_evidence(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    if payload.get("paper_trade_mode") is not True or payload.get("broker_execution_allowed") is not False:
        raise ValueError("Unsafe committee runtime evidence")
    steps = payload.get("committee_steps")
    if not isinstance(steps, list) or [step.get("committee_id") for step in steps] != list(COMMITTEES):
        raise ValueError("Committee runtime evidence must contain the frozen five-committee order")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, allow_nan=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_and_write_runtime_evidence(
    results_dir: str | Path,
    output_path: str | Path | None = None,
    *,
    generated_at_utc: str | None = None,
    paper_trade_mode: bool = True,
) -> Path:
    root = Path(results_dir)
    payload = build_runtime_evidence(root, generated_at_utc=generated_at_utc, paper_trade_mode=paper_trade_mode)
    return write_runtime_evidence(payload, output_path or root / "swing_committee_runtime_evidence.json")


def _step(committee_id: str, sequence: int, status: str, reasons: Sequence[str], evidence: Mapping[str, Any], sources: Sequence[str]) -> dict[str, Any]:
    return {
        "committee_id": committee_id,
        "sequence": sequence,
        "status": status,
        "reason_codes": list(reasons),
        "evidence": dict(evidence),
        "source_artifacts": sorted(set(sources)),
    }


def _read_json(path: Path) -> Any:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, (dict, list)):
        raise ValueError(f"JSON root must be an object or list: {path}")
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _rows(payload: Any, keys: Sequence[str] = ("rows", "candidates", "results")) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
    return []


def _optional_rows(path: Path, keys: Sequence[str] = ("rows", "candidates", "results")) -> list[Mapping[str, Any]]:
    return _rows(_read_json(path), keys) if path.is_file() else []


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
    return tier, rank, -_number(row, "composite_score"), _text(row, "underlying_symbol", "symbol")


def _find_symbol(rows: Sequence[Mapping[str, Any]], *symbols: str) -> Mapping[str, Any]:
    wanted = {symbol.upper() for symbol in symbols if symbol}
    for row in rows:
        symbol = _text(row, "symbol", "ticker", "underlying_symbol", "leveraged_symbol").upper()
        if symbol in wanted:
            return row
    return {}


def _value(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _text(row: Mapping[str, Any], *names: str, default: str = "") -> str:
    value = _value(row, *names)
    return default if value is None else str(value).strip()


def _optional_number(row: Mapping[str, Any], *names: str) -> float | None:
    value = _value(row, *names)
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).replace("%", "").replace(",", ""))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _number(row: Mapping[str, Any], *names: str) -> float:
    value = _optional_number(row, *names)
    return 0.0 if value is None else value


def _optional_int(row: Mapping[str, Any], *names: str) -> int | None:
    value = _optional_number(row, *names)
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

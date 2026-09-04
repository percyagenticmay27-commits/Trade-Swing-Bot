"""Read-only adapters from authoritative runtime reports to Promotion Readiness.

This module does not calculate Opportunity Quality, Entry Score, Thesis Health,
Financial Health, Theme Momentum, Theme Strength, or source confluence. It only
joins evidence already produced by the owning engines, keyed by the underlying
company symbol. Missing evidence remains None so Promotion Readiness reports
PENDING rather than manufacturing a zero.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from .enterprise_theme_strength import DEFAULT_AI_CIO_BUCKET, load_enterprise_theme_strength
from .promotion_readiness_engine import PromotionReadinessResult, evaluate_promotion_readiness, write_reports


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _rows(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not payload:
        return []
    for key in ("rows", "results", "candidates", "reviews"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    return []


def _symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("underlying_symbol", row.get("symbol", ""))).strip().upper()


def _index(payload: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    return {symbol: row for row in _rows(payload) if (symbol := _symbol(row))}


def _number(row: Mapping[str, Any] | None, *fields: str) -> float | None:
    if not row:
        return None
    for field in fields:
        value = row.get(field)
        if value is None or str(value).strip() == "":
            continue
        return float(value)
    return None


def _boolean(row: Mapping[str, Any] | None, *fields: str) -> bool | None:
    if not row:
        return None
    for field in fields:
        value = row.get(field)
        if isinstance(value, bool):
            return value
        if value is None or str(value).strip() == "":
            continue
        normalized = str(value).strip().lower()
        if normalized in {"true", "yes", "1", "pass", "intact", "strong"}:
            return True
        if normalized in {"false", "no", "0", "fail", "weakening", "broken"}:
            return False
    return None


def _is_current(payload: Mapping[str, Any] | None) -> bool:
    if payload is None:
        return False
    freshness = payload.get("freshness_status")
    return freshness is None or str(freshness).strip().upper() in {"CURRENT", "CURRENT_CYCLE", "FRESH"}


def build_promotion_readiness_from_runtime(
    results_dir: str | Path,
    *,
    watchlist_path: str | Path | None = None,
    opportunity_quality_path: str | Path | None = None,
    entry_score_path: str | Path | None = None,
    thesis_path: str | Path | None = None,
    theme_strength_path: str | Path = DEFAULT_AI_CIO_BUCKET,
    as_of: date | None = None,
) -> list[PromotionReadinessResult]:
    """Join current authoritative reports without recalculating their evidence."""
    root = Path(results_dir)
    paths = {
        "watchlist": Path(watchlist_path) if watchlist_path else root / "watchlist_report.json",
        "opportunity_quality": Path(opportunity_quality_path) if opportunity_quality_path else root / "opportunity_quality_report.json",
        "entry": Path(entry_score_path) if entry_score_path else root / "entry_score_report.json",
        "thesis": Path(thesis_path) if thesis_path else root / "thesis_monitor_v2_report.json",
        "theme_strength": Path(theme_strength_path),
    }
    payloads = {name: _load_json(path) for name, path in paths.items() if name != "theme_strength"}
    watchlist = payloads["watchlist"]
    if watchlist is None:
        raise FileNotFoundError(f"Promotion Readiness requires Watchlist evidence: {paths['watchlist']}")
    oq = _index(payloads["opportunity_quality"])
    entry = _index(payloads["entry"])
    thesis = _index(payloads["thesis"])
    theme_strength, _theme_audit, _theme_warnings = load_enterprise_theme_strength(
        paths["theme_strength"],
        as_of=as_of,
    )

    results: list[PromotionReadinessResult] = []
    for row in _rows(watchlist):
        symbol = _symbol(row)
        if not symbol:
            continue
        oq_row, entry_row, thesis_row = oq.get(symbol), entry.get(symbol), thesis.get(symbol)

        # Discovery Engine historically serialized absent Financial Health as 0.0.
        # Treat that legacy sentinel as unavailable unless a later authoritative
        # adapter supplies explicit evidence provenance. This prevents missing
        # company fundamentals from being misrepresented as a measured zero.
        health = _number(row, "financial_health_score")
        health_missing = health == 0.0

        # Theme Momentum remains a valid Swing discovery metric, but it is not the
        # Promotion Readiness Theme Strength gate. Theme Strength is accepted only
        # from the validated shared AI CIO contract above. There is no fallback to
        # watchlist theme_momentum_score when the shared block is missing/rejected.
        theme_evidence = theme_strength.get(symbol)
        theme_score = theme_evidence.score if theme_evidence is not None else None

        # Thesis Monitor v2 evidence availability takes precedence over the
        # thesis_intact boolean. Preserve legacy rows that do not expose
        # evidence_status, but never promote a non-evaluable v2 review.
        thesis_intact = _boolean(thesis_row, "thesis_intact", "intact")
        if thesis_row is not None and "evidence_status" in thesis_row:
            evidence_status = str(thesis_row.get("evidence_status", "")).strip().upper()
            if evidence_status != "AVAILABLE":
                thesis_intact = None

        results.append(evaluate_promotion_readiness(
            underlying_symbol=symbol,
            leveraged_symbol=str(row.get("leveraged_symbol", "")),
            lifecycle_status=str(row.get("watchlist_status", "")),
            source_confluence_score=_number(row, "source_confluence_score"),
            financial_health_score=None if health_missing else health,
            theme_momentum_score=theme_score,
            opportunity_quality_score=_number(oq_row, "opportunity_quality_score"),
            thesis_intact=thesis_intact,
            entry_score=_number(entry_row, "entry_score", "score"),
            stale={
                "trusted_sources": not _is_current(watchlist),
                "financial_health": not _is_current(watchlist),
                "theme_strength": False,
                "opportunity_quality": not _is_current(payloads["opportunity_quality"]),
                "entry": not _is_current(payloads["entry"]),
                "thesis_integrity": not _is_current(payloads["thesis"]),
            },
            evidence_sources={
                "trusted_sources": str(paths["watchlist"]),
                "financial_health": str(paths["watchlist"]),
                "theme_strength": str(paths["theme_strength"]),
                "opportunity_quality": str(paths["opportunity_quality"]),
                "entry": str(paths["entry"]),
                "thesis_integrity": str(paths["thesis"]),
            },
        ))
    return results


def build_and_write_promotion_readiness(results_dir: str | Path) -> tuple[Path, Path]:
    results = build_promotion_readiness_from_runtime(results_dir)
    return write_reports(results_dir, results)

"""Read-only adapter for authoritative AI CIO Enterprise Theme Strength evidence.

Promotion Readiness must not substitute Swing Theme Momentum for Theme Strength.
This module validates the shared AI CIO Theme Strength contract and returns only
complete, current, timestamped, provenanced evidence. Missing or malformed input
fails closed and remains unavailable to Promotion Readiness.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_AI_CIO_BUCKET = Path("/home/tradebot/Trade-Dividend-Bot/results/enterprise_swing_discovery_bucket.json")
MAX_ENTERPRISE_THEME_STRENGTH_AGE_DAYS = 7
REQUIRED_COMPONENTS = (
    "evidence_breadth",
    "source_class_diversity",
    "catalyst_support",
    "market_confirmation",
    "sector_confirmation",
)


@dataclass(frozen=True, slots=True)
class EnterpriseThemeStrengthEvidence:
    underlying_symbol: str
    score: float
    components: Mapping[str, float]
    evidence_timestamp: str
    provenance: str
    freshness_status: str


def _parse_timestamp(value: object) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("theme-strength evidence timestamp is required")
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("theme-strength evidence timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _score(value: object, field: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not 0.0 <= number <= 100.0:
        raise ValueError(f"{field} must be between 0 and 100")
    return number


def candidate_theme_strength_block(candidate: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = candidate.get("theme_strength")
    return value if isinstance(value, Mapping) else None


def parse_enterprise_theme_strength(
    underlying_symbol: str,
    payload: Mapping[str, Any],
    *,
    as_of: date,
    max_age_days: int = MAX_ENTERPRISE_THEME_STRENGTH_AGE_DAYS,
) -> EnterpriseThemeStrengthEvidence:
    if max_age_days < 0:
        raise ValueError("max_age_days must be nonnegative")
    symbol = str(underlying_symbol or "").strip().upper()
    if not symbol:
        raise ValueError("underlying_symbol is required")

    components_raw = payload.get("components")
    if not isinstance(components_raw, Mapping):
        raise ValueError("theme-strength components are required")
    components: dict[str, float] = {}
    for field in REQUIRED_COMPONENTS:
        if field not in components_raw:
            raise ValueError(f"missing required theme-strength component {field}")
        components[field] = _score(components_raw[field], field)

    score = _score(payload.get("score"), "theme_strength score")
    timestamp = _parse_timestamp(payload.get("evidence_timestamp"))
    provenance = str(payload.get("provenance") or "").strip()
    if not provenance:
        raise ValueError("theme-strength provenance is required")

    age_days = (as_of - timestamp.date()).days
    if age_days < -1:
        raise ValueError("theme-strength evidence timestamp is in the future")
    if age_days > max_age_days:
        raise ValueError(f"theme-strength evidence is stale ({age_days} days old)")

    return EnterpriseThemeStrengthEvidence(
        underlying_symbol=symbol,
        score=score,
        components=components,
        evidence_timestamp=timestamp.isoformat().replace("+00:00", "Z"),
        provenance=provenance,
        freshness_status="CURRENT",
    )


def load_enterprise_theme_strength(
    bucket_path: str | Path = DEFAULT_AI_CIO_BUCKET,
    *,
    as_of: date | None = None,
) -> tuple[dict[str, EnterpriseThemeStrengthEvidence], list[dict[str, Any]], list[str]]:
    """Load validated Theme Strength evidence keyed by underlying symbol."""
    source = Path(bucket_path)
    if not source.is_file():
        return {}, [], [f"AI_CIO_THEME_STRENGTH_BUCKET_MISSING:{source}"]
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Enterprise discovery bucket root must be an object")

    day = as_of or date.today()
    accepted: dict[str, EnterpriseThemeStrengthEvidence] = {}
    audit: list[dict[str, Any]] = []
    warnings: list[str] = []
    for candidate in payload.get("candidates", []):
        if not isinstance(candidate, Mapping):
            continue
        symbol = str(candidate.get("underlying_symbol") or "").strip().upper()
        if not symbol:
            continue
        block = candidate_theme_strength_block(candidate)
        if block is None:
            audit.append({"underlying_symbol": symbol, "status": "MISSING_ENTERPRISE_THEME_STRENGTH", "accepted": False})
            warnings.append(f"MISSING_REQUIRED_THEME_STRENGTH:{symbol}")
            continue
        try:
            evidence = parse_enterprise_theme_strength(symbol, block, as_of=day)
        except ValueError as exc:
            audit.append({
                "underlying_symbol": symbol,
                "status": "REJECTED_ENTERPRISE_THEME_STRENGTH",
                "accepted": False,
                "reason": str(exc),
            })
            warnings.append(f"INVALID_ENTERPRISE_THEME_STRENGTH:{symbol}:{exc}")
            continue
        accepted[symbol] = evidence
        audit.append({
            "underlying_symbol": symbol,
            "status": "ENTERPRISE_THEME_STRENGTH_ACCEPTED",
            "accepted": True,
            "score": evidence.score,
            "components": dict(evidence.components),
            "evidence_timestamp": evidence.evidence_timestamp,
            "provenance": evidence.provenance,
            "freshness_status": evidence.freshness_status,
        })
    return accepted, audit, list(dict.fromkeys(warnings))

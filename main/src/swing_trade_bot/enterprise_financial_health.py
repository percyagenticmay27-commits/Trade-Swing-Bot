"""Read-only financial-health adapter for Enterprise discovery candidates.

Swing's historical discovery engine expects seven 0-100 component scores. This
module does not invent a new scoring formula. It accepts only complete, timestamped,
provenanced AI CIO evidence already expressed in those existing Swing components,
and merges it with the existing trusted local health rows for runtime evaluation.
Missing or malformed Enterprise financial evidence remains missing and therefore
fails closed under the existing DiscoveryEngine thresholds.
"""
from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .discovery_engine import FINANCIAL_FIELDS, FinancialHealth

MAX_ENTERPRISE_FINANCIAL_AGE_DAYS = 14


@dataclass(frozen=True, slots=True)
class EnterpriseFinancialHealthEvidence:
    underlying_symbol: str
    health: FinancialHealth
    evidence_timestamp: str
    provenance: str
    freshness_status: str


def _parse_timestamp(value: object) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("evidence timestamp is required")
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("evidence timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _component(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not 0.0 <= number <= 100.0:
        raise ValueError(f"{field} must be between 0 and 100")
    return number


def parse_enterprise_financial_health(
    underlying_symbol: str,
    payload: Mapping[str, Any],
    *,
    as_of: date,
    max_age_days: int = MAX_ENTERPRISE_FINANCIAL_AGE_DAYS,
) -> EnterpriseFinancialHealthEvidence:
    """Validate one AI CIO financial-health block against Swing's existing model."""
    if max_age_days < 0:
        raise ValueError("max_age_days must be nonnegative")
    symbol = underlying_symbol.strip().upper()
    if not symbol:
        raise ValueError("underlying_symbol is required")

    components_raw = payload.get("components")
    components = components_raw if isinstance(components_raw, Mapping) else payload
    values: dict[str, float] = {}
    for field in FINANCIAL_FIELDS:
        if field not in components:
            raise ValueError(f"missing required financial-health component {field}")
        values[field] = _component(components[field], field)

    timestamp_raw = (
        payload.get("evidence_timestamp")
        or payload.get("generated_at_utc")
        or payload.get("generated_at")
        or payload.get("as_of")
    )
    timestamp = _parse_timestamp(timestamp_raw)
    provenance = str(
        payload.get("provenance")
        or payload.get("source")
        or payload.get("evidence_source")
        or ""
    ).strip()
    if not provenance:
        raise ValueError("financial-health provenance is required")

    age_days = (as_of - timestamp.date()).days
    if age_days < -1:
        raise ValueError("financial-health evidence timestamp is in the future")
    if age_days > max_age_days:
        raise ValueError(f"financial-health evidence is stale ({age_days} days old)")

    return EnterpriseFinancialHealthEvidence(
        underlying_symbol=symbol,
        health=FinancialHealth(**values),
        evidence_timestamp=timestamp.isoformat().replace("+00:00", "Z"),
        provenance=provenance,
        freshness_status="CURRENT" if age_days <= max_age_days else "STALE",
    )


def candidate_financial_health_block(candidate: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return a supported AI CIO financial-health object when present."""
    for key in ("financial_health", "financial_health_evidence"):
        value = candidate.get(key)
        if isinstance(value, Mapping):
            return value
    return None


def load_local_financial_health_rows(path: str | Path) -> dict[str, FinancialHealth]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Local financial-health source missing: {source}")
    result: dict[str, FinancialHealth] = {}
    with source.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("underlying_symbol", "")).strip().upper()
            if not symbol:
                raise ValueError("local financial-health row missing underlying_symbol")
            if symbol in result:
                raise ValueError(f"duplicate local financial-health symbol {symbol}")
            result[symbol] = FinancialHealth(
                **{field: _component(row.get(field), field) for field in FINANCIAL_FIELDS}
            )
    return result


def build_runtime_financial_health(
    *,
    local_path: str | Path,
    bucket: Mapping[str, Any] | None,
    as_of: date,
) -> tuple[dict[str, FinancialHealth], list[dict[str, Any]], list[str]]:
    """Merge local authority with validated Enterprise evidence.

    Existing local rows win for the same symbol so Enterprise discovery cannot
    silently overwrite historical Swing health evidence. Enterprise evidence fills
    only symbols absent from the local authority.
    """
    merged = load_local_financial_health_rows(local_path)
    audit: list[dict[str, Any]] = []
    warnings: list[str] = []
    if bucket is None:
        return merged, audit, warnings

    for candidate in bucket.get("candidates", []):
        if not isinstance(candidate, Mapping):
            continue
        symbol = str(candidate.get("underlying_symbol", "")).strip().upper()
        if not symbol:
            continue
        block = candidate_financial_health_block(candidate)
        if symbol in merged:
            audit.append(
                {
                    "underlying_symbol": symbol,
                    "status": "LOCAL_SWING_AUTHORITY_RETAINED",
                    "accepted": False,
                }
            )
            continue
        if block is None:
            audit.append(
                {
                    "underlying_symbol": symbol,
                    "status": "MISSING_ENTERPRISE_FINANCIAL_HEALTH",
                    "accepted": False,
                }
            )
            warnings.append(f"MISSING_REQUIRED_FINANCIAL_HEALTH:{symbol}")
            continue
        try:
            evidence = parse_enterprise_financial_health(symbol, block, as_of=as_of)
        except ValueError as exc:
            audit.append(
                {
                    "underlying_symbol": symbol,
                    "status": "REJECTED_ENTERPRISE_FINANCIAL_HEALTH",
                    "accepted": False,
                    "reason": str(exc),
                }
            )
            warnings.append(f"INVALID_ENTERPRISE_FINANCIAL_HEALTH:{symbol}:{exc}")
            continue
        merged[symbol] = evidence.health
        audit.append(
            {
                "underlying_symbol": symbol,
                "status": "ENTERPRISE_FINANCIAL_HEALTH_ACCEPTED",
                "accepted": True,
                "evidence_timestamp": evidence.evidence_timestamp,
                "provenance": evidence.provenance,
                "freshness_status": evidence.freshness_status,
                "score": round(evidence.health.score, 2),
            }
        )
    return merged, audit, list(dict.fromkeys(warnings))


def write_runtime_financial_health_csv(
    path: str | Path,
    rows: Mapping[str, FinancialHealth],
) -> Path:
    """Atomically materialize the runtime health input consumed by daily cycle."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            fieldnames = ["underlying_symbol", *FINANCIAL_FIELDS]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for symbol in sorted(rows):
                writer.writerow({"underlying_symbol": symbol, **asdict(rows[symbol])})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return destination

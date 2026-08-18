"""Read-only AI CIO discovery-bucket intake for Swing candidate discovery.

The Enterprise AI CIO may nominate underlying stocks and sectors for investigation.
This module never promotes a symbol into Swing lifecycle states, never places a
trade, and never writes to the AI CIO repository. New mapped underlyings enter
Swing only as DISCOVERY candidates. Existing Swing lifecycle/performance state
always wins over Enterprise nomination metadata.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .discovery_engine import CandidateState, SourceMention, load_candidates, load_mentions
from .enterprise_evidence_normalization import normalize_enterprise_source, source_class_profile

STRATEGY_ID = "SWING-001"
BUCKET_SCHEMA_VERSION = "1.0"
MAPPING_SCHEMA_VERSION = "1.0"
DEFAULT_AI_CIO_REPOSITORY = Path(
    os.environ.get("AI_CIO_REPOSITORY", "/home/tradebot/Trade-Dividend-Bot")
)
DEFAULT_BUCKET_RELATIVE_PATH = Path("results/enterprise_swing_discovery_bucket.json")
DEFAULT_MAPPING_RELATIVE_PATH = Path("configs/swing_discovery_leveraged_mapping.json")
DEFAULT_LOCAL_CANDIDATES_RELATIVE_PATH = Path("examples/discovery_candidates.csv")
DEFAULT_LOCAL_MENTIONS_RELATIVE_PATH = Path("results/discovery_mentions.csv")
DEFAULT_RUNTIME_CANDIDATES_RELATIVE_PATH = Path("results/discovery_candidates_runtime.csv")
DEFAULT_RUNTIME_MENTIONS_RELATIVE_PATH = Path("results/discovery_mentions_runtime.csv")
DEFAULT_INTAKE_REPORT_RELATIVE_PATH = Path("results/enterprise_discovery_intake_report.json")
IMPORTABLE_BUCKET_STATUSES = frozenset({"HOT", "RISING", "EMERGING"})
VALID_BUCKET_STATUSES = frozenset({"HOT", "RISING", "EMERGING", "COOLING", "DECLINING"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {source}")
    return payload


def discover_bucket_path(
    *,
    repository_root: str | Path | None = None,
    relative_path: str | Path = DEFAULT_BUCKET_RELATIVE_PATH,
) -> Path:
    """Return the configured read-only AI CIO discovery-bucket path."""
    root = Path(repository_root) if repository_root is not None else DEFAULT_AI_CIO_REPOSITORY
    return root / Path(relative_path)


def load_discovery_bucket(path: str | Path) -> dict[str, Any]:
    """Load and validate an Enterprise discovery bucket without changing Swing state."""
    payload = _load_json_object(path)
    if str(payload.get("schema_version", "")).strip() != BUCKET_SCHEMA_VERSION:
        raise ValueError("discovery bucket schema_version must be 1.0")
    target = str(payload.get("strategy_id", STRATEGY_ID)).strip()
    if target and target != STRATEGY_ID:
        raise ValueError(f"discovery bucket strategy_id must be {STRATEGY_ID}")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("discovery bucket candidates must be a list")
    seen: set[str] = set()
    for index, item in enumerate(candidates):
        if not isinstance(item, Mapping):
            raise ValueError(f"discovery bucket candidates[{index}] must be an object")
        symbol = str(item.get("underlying_symbol", "")).strip().upper()
        if not symbol:
            raise ValueError(f"discovery bucket candidates[{index}].underlying_symbol is required")
        if symbol in seen:
            raise ValueError(f"discovery bucket contains duplicate underlying_symbol {symbol}")
        seen.add(symbol)
        status = str(item.get("discovery_status", "")).strip().upper()
        if status not in VALID_BUCKET_STATUSES:
            raise ValueError(
                f"discovery bucket candidates[{index}].discovery_status must be one of "
                + ", ".join(sorted(VALID_BUCKET_STATUSES))
            )
        evidence = item.get("evidence_sources", [])
        if not isinstance(evidence, list):
            raise ValueError(f"discovery bucket candidates[{index}].evidence_sources must be a list")
        for evidence_index, evidence_item in enumerate(evidence):
            if not isinstance(evidence_item, Mapping):
                raise ValueError(
                    f"discovery bucket candidates[{index}].evidence_sources[{evidence_index}] must be an object"
                )
    return payload


def load_leveraged_mapping(path: str | Path) -> dict[str, str]:
    """Load explicit underlying-to-leveraged mappings owned by Swing.

    No ticker relationship is inferred from symbol spelling.
    """
    payload = _load_json_object(path)
    if str(payload.get("schema_version", "")).strip() != MAPPING_SCHEMA_VERSION:
        raise ValueError("leveraged mapping schema_version must be 1.0")
    mappings = payload.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("leveraged mapping mappings must be a list")
    result: dict[str, str] = {}
    leveraged_seen: set[str] = set()
    for index, item in enumerate(mappings):
        if not isinstance(item, Mapping):
            raise ValueError(f"leveraged mapping mappings[{index}] must be an object")
        if item.get("enabled", True) is not True:
            continue
        underlying = str(item.get("underlying_symbol", "")).strip().upper()
        leveraged = str(item.get("leveraged_symbol", "")).strip().upper()
        if not underlying or not leveraged:
            raise ValueError(
                f"leveraged mapping mappings[{index}] requires underlying_symbol and leveraged_symbol"
            )
        if underlying in result:
            raise ValueError(f"duplicate leveraged mapping for underlying {underlying}")
        if leveraged in leveraged_seen:
            raise ValueError(f"duplicate leveraged_symbol mapping {leveraged}")
        result[underlying] = leveraged
        leveraged_seen.add(leveraged)
    return result


def _themes(item: Mapping[str, Any]) -> tuple[str, ...]:
    value = item.get("themes", [])
    if isinstance(value, str):
        values = value.replace("|", ";").split(";")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = value
    else:
        values = []
    ordered: list[str] = []
    normalized: set[str] = set()
    for raw in values:
        theme = str(raw).strip()
        key = theme.upper()
        if theme and key not in normalized:
            ordered.append(theme)
            normalized.add(key)
    return tuple(ordered)


def _merge_themes(existing: Sequence[str], incoming: Sequence[str]) -> tuple[str, ...]:
    ordered = list(existing)
    normalized = {theme.upper() for theme in ordered}
    for theme in incoming:
        if theme.upper() not in normalized:
            ordered.append(theme)
            normalized.add(theme.upper())
    return tuple(ordered)


def merge_bucket_candidates(
    existing: Sequence[CandidateState],
    bucket: Mapping[str, Any],
    leveraged_mapping: Mapping[str, str],
) -> tuple[list[CandidateState], list[str]]:
    """Merge AI CIO nominations into Swing candidates without promoting lifecycle state.

    Existing Swing rows retain status, paper performance, and their current leveraged
    symbol. New eligible bucket rows are admitted only when Swing has an explicit
    leveraged mapping; they always start at DISCOVERY with zero paper history.
    """
    merged = list(existing)
    index_by_symbol = {item.underlying_symbol.strip().upper(): idx for idx, item in enumerate(merged)}
    warnings: list[str] = []

    for item in bucket.get("candidates", []):
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("underlying_symbol", "")).strip().upper()
        bucket_status = str(item.get("discovery_status", "")).strip().upper()
        incoming_themes = _themes(item)

        if symbol in index_by_symbol:
            idx = index_by_symbol[symbol]
            current = merged[idx]
            merged[idx] = replace(current, themes=_merge_themes(current.themes, incoming_themes))
            continue

        if bucket_status not in IMPORTABLE_BUCKET_STATUSES:
            continue
        leveraged_symbol = leveraged_mapping.get(symbol)
        if not leveraged_symbol:
            warnings.append(f"NO_APPROVED_LEVERAGED_MAPPING:{symbol}")
            continue
        merged.append(
            CandidateState(
                underlying_symbol=symbol,
                leveraged_symbol=leveraged_symbol,
                status="DISCOVERY",
                paper_return=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                number_of_trades=0,
                trading_days=0,
                days_in_status=0,
                earnings_stability_score=50.0,
                leveraged_vehicle_exists=True,
                themes=incoming_themes,
            )
        )
        index_by_symbol[symbol] = len(merged) - 1
    return merged, warnings


def bucket_mentions_with_audit(
    bucket: Mapping[str, Any],
) -> tuple[list[SourceMention], list[dict[str, Any]], list[str]]:
    """Normalize AI CIO source evidence and retain original-source audit provenance."""
    mentions: list[SourceMention] = []
    audit: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, date]] = set()

    for candidate in bucket.get("candidates", []):
        if not isinstance(candidate, Mapping):
            continue
        symbol = str(candidate.get("underlying_symbol", "")).strip().upper()
        candidate_themes = _themes(candidate)
        for evidence_index, evidence in enumerate(candidate.get("evidence_sources", [])):
            if not isinstance(evidence, Mapping):
                continue
            normalized = normalize_enterprise_source(
                evidence.get("source"),
                evidence.get("source_class"),
            )
            audit_row: dict[str, Any] = {
                "underlying_symbol": symbol,
                "evidence_index": evidence_index,
                "original_source": normalized.original_source,
                "supplied_source_class": str(evidence.get("source_class", "")).strip() or None,
                "normalized_source_class": normalized.source_class,
                "normalization_method": normalized.normalization_method,
                "accepted": normalized.accepted,
            }
            if not normalized.accepted:
                if normalized.warning:
                    warnings.append(normalized.warning)
                    audit_row["reason"] = normalized.warning
                audit.append(audit_row)
                continue

            mentioned_on_raw = str(evidence.get("mentioned_on", "")).strip()
            if not mentioned_on_raw:
                warning = f"MALFORMED_ENTERPRISE_EVIDENCE:{symbol}:{normalized.original_source}:MISSING_MENTIONED_ON"
                warnings.append(warning)
                audit_row.update({"accepted": False, "reason": warning})
                audit.append(audit_row)
                continue
            try:
                mentioned_on = date.fromisoformat(mentioned_on_raw)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid mentioned_on for {symbol}/{normalized.original_source}: {mentioned_on_raw}"
                ) from exc

            key = (symbol, normalized.original_source.strip().upper(), mentioned_on)
            if key in seen:
                audit_row.update({"accepted": False, "duplicate": True, "reason": "DUPLICATE_ENTERPRISE_EVIDENCE"})
                audit.append(audit_row)
                continue
            seen.add(key)

            profile = source_class_profile(normalized.source_class)
            evidence_themes = _themes(evidence)
            mentions.append(
                SourceMention(
                    underlying_symbol=symbol,
                    source=normalized.original_source,
                    original_source=normalized.original_source,
                    source_class=normalized.source_class,
                    mentioned_on=mentioned_on,
                    themes=_merge_themes(candidate_themes, evidence_themes),
                    earnings_growth_related=evidence.get("earnings_growth_related") is True,
                    analyst_upgrade_related=evidence.get("analyst_upgrade_related") is True,
                )
            )
            audit_row.update(
                {
                    "mentioned_on": mentioned_on.isoformat(),
                    "trusted_weight": profile.weight if profile else 0,
                    "institutional": bool(profile and profile.institutional),
                    "creator": bool(profile and profile.youtube_or_creator),
                }
            )
            audit.append(audit_row)

    return mentions, audit, list(dict.fromkeys(warnings))


def bucket_mentions(bucket: Mapping[str, Any]) -> list[SourceMention]:
    """Translate normalized source-level AI CIO evidence into Swing mentions."""
    mentions, _, _ = bucket_mentions_with_audit(bucket)
    return mentions


def _mention_identity(mention: SourceMention) -> str:
    return (mention.original_source or mention.source).strip().upper()


def merge_mentions(
    local_mentions: Sequence[SourceMention],
    enterprise_mentions: Sequence[SourceMention],
) -> list[SourceMention]:
    """Merge local and Enterprise evidence, deduplicated by symbol/source/date."""
    result: list[SourceMention] = []
    seen: set[tuple[str, str, date]] = set()
    for mention in (*local_mentions, *enterprise_mentions):
        key = (
            mention.underlying_symbol.strip().upper(),
            _mention_identity(mention),
            mention.mentioned_on,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(mention)
    return result


def write_candidates_csv(path: str | Path, candidates: Sequence[CandidateState]) -> Path:
    """Materialize the merged runtime candidate universe for the daily Swing cycle."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(CandidateState.__dataclass_fields__)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            row = asdict(candidate)
            row["themes"] = ";".join(candidate.themes)
            writer.writerow(row)
    return destination


def write_mentions_csv(path: str | Path, mentions: Sequence[SourceMention]) -> Path:
    """Materialize merged local + normalized AI CIO source evidence."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "underlying_symbol",
        "source",
        "original_source",
        "source_class",
        "mentioned_on",
        "themes",
        "earnings_growth_related",
        "analyst_upgrade_related",
    )
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for mention in mentions:
            writer.writerow(
                {
                    "underlying_symbol": mention.underlying_symbol,
                    "source": mention.source,
                    "original_source": mention.original_source or "",
                    "source_class": mention.source_class or "",
                    "mentioned_on": mention.mentioned_on.isoformat(),
                    "themes": ";".join(mention.themes),
                    "earnings_growth_related": str(mention.earnings_growth_related).lower(),
                    "analyst_upgrade_related": str(mention.analyst_upgrade_related).lower(),
                }
            )
    return destination


def refresh_enterprise_discovery_inputs(
    *,
    swing_root: str | Path | None = None,
    ai_cio_repository: str | Path | None = None,
) -> dict[str, Any]:
    """Build current runtime discovery inputs before the normal Swing cycle.

    The AI CIO bucket is optional. If it does not yet exist, current Swing-local
    candidates and mentions are materialized unchanged so the existing cycle can
    continue safely. A malformed bucket fails closed instead of silently importing
    unverifiable candidates.
    """
    root = Path(swing_root) if swing_root is not None else Path.cwd()
    local_candidates_path = root / DEFAULT_LOCAL_CANDIDATES_RELATIVE_PATH
    local_mentions_path = root / DEFAULT_LOCAL_MENTIONS_RELATIVE_PATH
    mapping_path = root / DEFAULT_MAPPING_RELATIVE_PATH
    runtime_candidates_path = root / DEFAULT_RUNTIME_CANDIDATES_RELATIVE_PATH
    runtime_mentions_path = root / DEFAULT_RUNTIME_MENTIONS_RELATIVE_PATH
    report_path = root / DEFAULT_INTAKE_REPORT_RELATIVE_PATH

    if not local_candidates_path.is_file():
        raise FileNotFoundError(f"Swing local discovery candidates missing: {local_candidates_path}")
    if not local_mentions_path.is_file():
        raise FileNotFoundError(f"Swing local discovery mentions missing: {local_mentions_path}")
    if not mapping_path.is_file():
        raise FileNotFoundError(f"Swing leveraged mapping missing: {mapping_path}")

    candidates = load_candidates(local_candidates_path)
    mentions = load_mentions(local_mentions_path)
    mapping = load_leveraged_mapping(mapping_path)
    bucket_path = discover_bucket_path(repository_root=ai_cio_repository)
    bucket_available = bucket_path.is_file()
    warnings: list[str] = []
    enterprise_candidate_count = 0
    enterprise_mention_count = 0
    evidence_received = 0
    evidence_normalized = 0
    evidence_rejected = 0
    evidence_audit: list[dict[str, Any]] = []
    bucket_generated_at = None

    if bucket_available:
        bucket = load_discovery_bucket(bucket_path)
        bucket_generated_at = bucket.get("generated_at_utc") or bucket.get("generated_at")
        enterprise_candidate_count = len(bucket.get("candidates", []))
        evidence_received = sum(
            len(item.get("evidence_sources", []))
            for item in bucket.get("candidates", [])
            if isinstance(item, Mapping)
        )
        candidates, candidate_warnings = merge_bucket_candidates(candidates, bucket, mapping)
        enterprise_mentions, evidence_audit, evidence_warnings = bucket_mentions_with_audit(bucket)
        warnings.extend(candidate_warnings)
        warnings.extend(evidence_warnings)
        enterprise_mention_count = len(enterprise_mentions)
        evidence_normalized = sum(1 for row in evidence_audit if row.get("accepted") is True)
        evidence_rejected = evidence_received - evidence_normalized
        mentions = merge_mentions(mentions, enterprise_mentions)

    write_candidates_csv(runtime_candidates_path, candidates)
    write_mentions_csv(runtime_mentions_path, mentions)
    report = {
        "schema_version": "1.1",
        "strategy_id": STRATEGY_ID,
        "paper_trade_mode": True,
        "generated_at_utc": _utc_now(),
        "source_mode": "AI_CIO_BUCKET_PLUS_SWING_LOCAL" if bucket_available else "SWING_LOCAL_FALLBACK",
        "ai_cio_bucket_available": bucket_available,
        "ai_cio_bucket_readable": bucket_available,
        "ai_cio_bucket_schema_valid": bucket_available,
        "ai_cio_bucket_path": str(bucket_path),
        "ai_cio_bucket_generated_at": bucket_generated_at,
        "local_candidates_path": str(local_candidates_path),
        "local_mentions_path": str(local_mentions_path),
        "leveraged_mapping_path": str(mapping_path),
        "runtime_candidates_path": str(runtime_candidates_path),
        "runtime_mentions_path": str(runtime_mentions_path),
        "enterprise_candidate_count": enterprise_candidate_count,
        "enterprise_mention_count": enterprise_mention_count,
        "enterprise_evidence_records_received": evidence_received,
        "enterprise_evidence_records_normalized": evidence_normalized,
        "enterprise_evidence_records_rejected": evidence_rejected,
        "enterprise_evidence_normalization_audit": evidence_audit,
        "runtime_candidate_count": len(candidates),
        "runtime_mention_count": len(mentions),
        "warnings": list(dict.fromkeys(warnings)),
        "errors": [],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report

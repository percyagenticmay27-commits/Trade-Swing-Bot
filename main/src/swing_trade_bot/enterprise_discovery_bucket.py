"""Read-only AI CIO discovery-bucket intake for Swing candidate discovery.

The Enterprise AI CIO may nominate underlying stocks and sectors for investigation.
This module never promotes a symbol into Swing lifecycle states, never places a
trade, and never writes to the AI CIO repository. New mapped underlyings enter
Swing only as DISCOVERY candidates. Existing Swing lifecycle/performance state
always wins over Enterprise nomination metadata.
"""
from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from .discovery_engine import CandidateState, SourceMention

STRATEGY_ID = "SWING-001"
BUCKET_SCHEMA_VERSION = "1.0"
MAPPING_SCHEMA_VERSION = "1.0"
DEFAULT_AI_CIO_REPOSITORY = Path(
    os.environ.get("AI_CIO_REPOSITORY", "/home/tradebot/Trade-Dividend-Bot")
)
DEFAULT_BUCKET_RELATIVE_PATH = Path("results/enterprise_swing_discovery_bucket.json")
DEFAULT_MAPPING_RELATIVE_PATH = Path("configs/swing_discovery_leveraged_mapping.json")
IMPORTABLE_BUCKET_STATUSES = frozenset({"HOT", "RISING", "EMERGING"})
VALID_BUCKET_STATUSES = frozenset({"HOT", "RISING", "EMERGING", "COOLING", "DECLINING"})


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
    for raw in values:
        theme = str(raw).strip()
        if theme and theme.upper() not in {existing.upper() for existing in ordered}:
            ordered.append(theme)
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


def bucket_mentions(bucket: Mapping[str, Any]) -> list[SourceMention]:
    """Translate source-level AI CIO evidence into Swing discovery mentions."""
    mentions: list[SourceMention] = []
    seen: set[tuple[str, str, date]] = set()
    for candidate in bucket.get("candidates", []):
        if not isinstance(candidate, Mapping):
            continue
        symbol = str(candidate.get("underlying_symbol", "")).strip().upper()
        candidate_themes = _themes(candidate)
        for evidence in candidate.get("evidence_sources", []):
            if not isinstance(evidence, Mapping):
                continue
            source = str(evidence.get("source", "")).strip()
            mentioned_on_raw = str(evidence.get("mentioned_on", "")).strip()
            if not source or not mentioned_on_raw:
                continue
            try:
                mentioned_on = date.fromisoformat(mentioned_on_raw)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid mentioned_on for {symbol}/{source}: {mentioned_on_raw}"
                ) from exc
            key = (symbol, source.upper(), mentioned_on)
            if key in seen:
                continue
            seen.add(key)
            evidence_themes = _themes(evidence)
            mentions.append(
                SourceMention(
                    underlying_symbol=symbol,
                    source=source,
                    mentioned_on=mentioned_on,
                    themes=_merge_themes(candidate_themes, evidence_themes),
                    earnings_growth_related=evidence.get("earnings_growth_related") is True,
                    analyst_upgrade_related=evidence.get("analyst_upgrade_related") is True,
                )
            )
    return mentions


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
            mention.source.strip().upper(),
            mention.mentioned_on,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(mention)
    return result

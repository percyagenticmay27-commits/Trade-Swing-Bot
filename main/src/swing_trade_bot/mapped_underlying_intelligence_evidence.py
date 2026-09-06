"""Swing-owned Market Intelligence and Conviction evidence for mapped underlyings.

This module reuses the existing 30-day source-confluence semantics. AI CIO
HOT/RISING/EMERGING status is never a score. Only dated, normalized evidence
sources contribute, and Conviction requires at least two independent trusted
sources so a single article or creator cannot manufacture high confidence.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from .discovery_engine import (
    SourceMention,
    _independent_scoring_mentions,
    _mention_is_institutional,
    _mention_is_youtube_or_creator,
    _mention_weight,
    load_mentions,
)
from .leveraged_vehicle_registry import preferred_vehicle_mapping

OUTPUT_NAME = "mapped_underlying_intelligence_evidence.json"
ROLLING_DAYS = 30
MIN_CONVICTION_SOURCES = 2
DEFAULT_MENTION_FILES = (
    "discovery_mentions_runtime.csv",
    "mapped_underlying_news_mentions.csv",
)


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _recent_mentions(symbol: str, mentions: Sequence[SourceMention], as_of: date) -> list[SourceMention]:
    cutoff = as_of - timedelta(days=ROLLING_DAYS)
    return [
        mention
        for mention in mentions
        if mention.underlying_symbol.strip().upper() == symbol
        and cutoff <= mention.mentioned_on <= as_of
    ]


def _merge_mentions(mention_sets: Sequence[Sequence[SourceMention]]) -> list[SourceMention]:
    result: list[SourceMention] = []
    seen: set[tuple[str, str, date]] = set()
    for mentions in mention_sets:
        for mention in mentions:
            identity = (
                mention.underlying_symbol.strip().upper(),
                (mention.original_source or mention.source).strip().upper(),
                mention.mentioned_on,
            )
            if identity in seen:
                continue
            seen.add(identity)
            result.append(mention)
    return result


def _recency_score(freshest_age_days: int) -> float:
    if freshest_age_days <= 7:
        return 25.0
    if freshest_age_days <= 14:
        return 18.0
    if freshest_age_days <= 21:
        return 10.0
    return 5.0


def score_intelligence_mentions(
    mentions: Sequence[SourceMention], *, as_of: date
) -> dict[str, Any] | None:
    trusted = _independent_scoring_mentions(list(mentions))
    trusted = [item for item in trusted if _mention_weight(item, list(mentions)) > 0]
    if not trusted:
        return None

    source_count = len(trusted)
    institutional_count = sum(_mention_is_institutional(item, list(mentions)) for item in trusted)
    creator_count = sum(_mention_is_youtube_or_creator(item, list(mentions)) for item in trusted)
    weighted_confluence = sum(_mention_weight(item, list(mentions)) for item in trusted)
    freshest_age = min((as_of - item.mentioned_on).days for item in trusted)
    earnings_catalyst = any(item.earnings_growth_related for item in trusted)
    upgrade_catalyst = any(item.analyst_upgrade_related for item in trusted)

    market_intelligence = (
        min(source_count / 4.0, 1.0) * 30.0
        + min(institutional_count / 3.0, 1.0) * 25.0
        + (10.0 if earnings_catalyst else 0.0)
        + (10.0 if upgrade_catalyst else 0.0)
        + _recency_score(freshest_age)
    )

    source_classes = {
        str(item.source_class or item.source).strip().upper()
        for item in trusted
        if str(item.source_class or item.source).strip()
    }
    class_diversity = len(source_classes)
    corroborated_catalysts = sum(1 for flag in (earnings_catalyst, upgrade_catalyst) if flag)

    conviction: float | None = None
    if source_count >= MIN_CONVICTION_SOURCES:
        conviction = (
            min(weighted_confluence / 10.0, 1.0) * 45.0
            + min(source_count / 4.0, 1.0) * 20.0
            + min(class_diversity / 3.0, 1.0) * 20.0
            + (10.0 if institutional_count > 0 and creator_count > 0 else 0.0)
            + min(corroborated_catalysts / 2.0, 1.0) * 5.0
        )

    return {
        "market_intelligence_score": _clamp(market_intelligence),
        "conviction_score": _clamp(conviction) if conviction is not None else None,
        "trusted_source_count": source_count,
        "institutional_source_count": institutional_count,
        "creator_source_count": creator_count,
        "weighted_confluence": weighted_confluence,
        "source_class_count": class_diversity,
        "freshest_evidence_age_days": freshest_age,
        "earnings_growth_catalyst": earnings_catalyst,
        "analyst_upgrade_catalyst": upgrade_catalyst,
        "sources": [
            {
                "source": item.original_source or item.source,
                "source_class": item.source_class,
                "mentioned_on": item.mentioned_on.isoformat(),
                "weight": _mention_weight(item, list(mentions)),
            }
            for item in trusted
        ],
    }


def build_mapped_underlying_intelligence_evidence(
    *,
    registry_path: str | Path,
    mentions: Sequence[SourceMention],
    as_of: date,
) -> dict[str, Any]:
    mapping = preferred_vehicle_mapping(registry_path)
    rows: list[dict[str, Any]] = []
    intelligence_count = 0
    conviction_count = 0
    for symbol in sorted(mapping):
        recent = _recent_mentions(symbol, mentions, as_of)
        scored = score_intelligence_mentions(recent, as_of=as_of)
        if scored is None:
            rows.append({
                "underlying_symbol": symbol,
                "preferred_vehicle": mapping[symbol],
                "market_intelligence_score": None,
                "conviction_score": None,
                "evidence_status": "MISSING_TRUSTED_RECENT_SOURCE_EVIDENCE",
                "rolling_days": ROLLING_DAYS,
            })
            continue
        intelligence_count += 1
        if scored["conviction_score"] is not None:
            conviction_count += 1
        rows.append({
            "underlying_symbol": symbol,
            "preferred_vehicle": mapping[symbol],
            **scored,
            "evidence_status": "AVAILABLE" if scored["conviction_score"] is not None else "INTELLIGENCE_ONLY_INSUFFICIENT_CONFLUENCE",
            "rolling_days": ROLLING_DAYS,
        })
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "ai_cio_discovery_status_used_as_score": False,
        "mapped_underlying_count": len(mapping),
        "underlyings_with_market_intelligence": intelligence_count,
        "underlyings_with_conviction": conviction_count,
        "rows": rows,
    }


def build_and_write_mapped_underlying_intelligence_evidence(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    mentions_path: str | Path | None = None,
    mentions_paths: Sequence[str | Path] | None = None,
    output_dir: str | Path = "results",
    as_of: date | None = None,
) -> dict[str, Any]:
    root = Path(output_dir)
    if mentions_paths is not None:
        sources = [Path(path) for path in mentions_paths]
    elif mentions_path is not None:
        sources = [Path(mentions_path)]
    else:
        sources = [root / name for name in DEFAULT_MENTION_FILES]
    mention_sets = [load_mentions(path) for path in sources if path.is_file()]
    mentions = _merge_mentions(mention_sets)
    payload = build_mapped_underlying_intelligence_evidence(
        registry_path=registry_path,
        mentions=mentions,
        as_of=as_of or date.today(),
    )
    root.mkdir(parents=True, exist_ok=True)
    path = root / OUTPUT_NAME
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=root) as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return payload


if __name__ == "__main__":
    report = build_and_write_mapped_underlying_intelligence_evidence()
    print(
        "Mapped underlying intelligence evidence: "
        f"{report['underlyings_with_market_intelligence']}/{report['mapped_underlying_count']} intelligence; "
        f"{report['underlyings_with_conviction']}/{report['mapped_underlying_count']} conviction"
    )

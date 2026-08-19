from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from swing_trade_bot.discovery_engine import SourceMention
from swing_trade_bot.mapped_underlying_intelligence_evidence import (
    build_mapped_underlying_intelligence_evidence,
    score_intelligence_mentions,
)


def _registry(path: Path) -> Path:
    payload = {
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mapping_policy": "EXPLICIT_VERIFIED_ONE_TO_MANY_NO_TICKER_INFERENCE",
        "review_policy": {"cadence": "WEEKLY_WEEKEND", "preferred_vehicle_scope": "FUTURE_NEW_CANDIDATES_ONLY", "existing_positions_unchanged": True, "switch_threshold_points": 5.0},
        "mappings": [{"underlying_symbol": "NVDA", "preferred_vehicle": "NVDX", "vehicles": [{"symbol": "NVDX", "verified": True, "enabled": True}]}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _mention(source: str, source_class: str, days_ago: int, *, earnings: bool = False, upgrade: bool = False) -> SourceMention:
    today = date(2026, 8, 18)
    return SourceMention(
        underlying_symbol="NVDA",
        source=source,
        original_source=source,
        source_class=source_class,
        mentioned_on=today - timedelta(days=days_ago),
        earnings_growth_related=earnings,
        analyst_upgrade_related=upgrade,
    )


def test_multiple_trusted_sources_generate_market_intelligence_and_conviction() -> None:
    mentions = [
        _mention("Reuters", "INSTITUTIONAL_NEWS", 2, earnings=True),
        _mention("SEC Filing", "PRIMARY_REGULATORY", 5),
        _mention("Ticker Symbol: YOU", "PROFESSIONAL_CREATOR", 6, upgrade=True),
    ]
    result = score_intelligence_mentions(mentions, as_of=date(2026, 8, 18))
    assert result is not None
    assert 0 <= result["market_intelligence_score"] <= 100
    assert 0 <= result["conviction_score"] <= 100
    assert result["trusted_source_count"] == 3
    assert result["institutional_source_count"] == 2
    assert result["creator_source_count"] == 1


def test_single_trusted_source_can_create_intelligence_but_not_conviction() -> None:
    result = score_intelligence_mentions(
        [_mention("Reuters", "INSTITUTIONAL_NEWS", 3)],
        as_of=date(2026, 8, 18),
    )
    assert result is not None
    assert result["market_intelligence_score"] is not None
    assert result["conviction_score"] is None


def test_social_only_evidence_cannot_create_scores() -> None:
    result = score_intelligence_mentions(
        [_mention("StockTwits", "SOCIAL_COMMUNITY", 1)],
        as_of=date(2026, 8, 18),
    )
    assert result is None


def test_stale_mentions_outside_30_days_are_missing(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_intelligence_evidence(
        registry_path=registry,
        mentions=[_mention("Reuters", "INSTITUTIONAL_NEWS", 31)],
        as_of=date(2026, 8, 18),
    )
    row = report["rows"][0]
    assert row["market_intelligence_score"] is None
    assert row["conviction_score"] is None


def test_ai_cio_status_is_not_a_scoring_input(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_intelligence_evidence(
        registry_path=registry,
        mentions=[],
        as_of=date(2026, 8, 18),
    )
    assert report["ai_cio_discovery_status_used_as_score"] is False
    assert report["underlyings_with_market_intelligence"] == 0


def test_intelligence_evidence_is_paper_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = build_mapped_underlying_intelligence_evidence(
        registry_path=registry,
        mentions=[],
        as_of=date(2026, 8, 18),
    )
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False

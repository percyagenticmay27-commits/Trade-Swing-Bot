from __future__ import annotations

import csv
import json
from pathlib import Path

from swing_trade_bot.discovery_engine import FinancialHealth, load_candidates, load_mentions
from swing_trade_bot.enterprise_discovery_bucket import (
    mapped_news_mentions,
    refresh_enterprise_discovery_inputs,
)
from swing_trade_bot.theme_enriched_discovery import ThemeEnrichedDiscoveryEngine


def _write_mapping(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "SWING-001",
                "paper_trade_mode": True,
                "mappings": [
                    {
                        "underlying_symbol": "NVDA",
                        "leveraged_symbol": "NVDX",
                        "enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_mapped_news(path: Path, *, source_class: str = "INSTITUTIONAL_NEWS") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "underlying_symbol",
                "source",
                "original_source",
                "source_class",
                "mentioned_on",
                "themes",
                "earnings_growth_related",
                "analyst_upgrade_related",
                "headline",
                "url",
                "scoring_eligible",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "underlying_symbol": "NVDA",
                "source": "Reuters",
                "original_source": "Reuters",
                "source_class": source_class,
                "mentioned_on": "2026-09-03",
                "themes": "",
                "earnings_growth_related": "true",
                "analyst_upgrade_related": "false",
                "headline": "Nvidia AI data center GPU accelerator demand remains strong",
                "url": "https://example.com/nvda",
                "scoring_eligible": "true",
            }
        )


def test_mapped_news_derives_only_existing_approved_theme_tags(tmp_path: Path) -> None:
    path = tmp_path / "mapped_underlying_news_mentions.csv"
    _write_mapped_news(path)

    mentions = mapped_news_mentions(path)

    assert len(mentions) == 1
    assert mentions[0].underlying_symbol == "NVDA"
    assert mentions[0].themes == (
        "AI Infrastructure",
        "Data Centers",
        "Semiconductors",
    )
    assert mentions[0].source_class == "INSTITUTIONAL_NEWS"


def test_missing_mapped_news_is_optional_and_does_not_invent_themes(tmp_path: Path) -> None:
    assert mapped_news_mentions(tmp_path / "missing.csv") == []


def test_refresh_merges_mapped_news_for_existing_watchlist_without_changing_lifecycle(tmp_path: Path) -> None:
    candidates = tmp_path / "examples/discovery_candidates.csv"
    candidates.parent.mkdir(parents=True, exist_ok=True)
    candidates.write_text(
        "underlying_symbol,leveraged_symbol,status,paper_return,win_rate,profit_factor,number_of_trades,trading_days,days_in_status,earnings_stability_score,leveraged_vehicle_exists,themes\n"
        "NVDA,NVDX,WATCHLIST,0,0,0,0,0,11,50,true,\n",
        encoding="utf-8",
    )
    mentions = tmp_path / "results/discovery_mentions.csv"
    mentions.parent.mkdir(parents=True, exist_ok=True)
    mentions.write_text(
        "underlying_symbol,source,mentioned_on,themes,earnings_growth_related,analyst_upgrade_related\n",
        encoding="utf-8",
    )
    _write_mapping(tmp_path / "configs/swing_discovery_leveraged_mapping.json")
    _write_mapped_news(tmp_path / "results/mapped_underlying_news_mentions.csv")

    report = refresh_enterprise_discovery_inputs(
        swing_root=tmp_path,
        ai_cio_repository=tmp_path / "missing-ai-cio",
    )

    runtime_candidates = load_candidates(tmp_path / "results/discovery_candidates_runtime.csv")
    runtime_mentions = load_mentions(tmp_path / "results/discovery_mentions_runtime.csv")
    assert runtime_candidates[0].status == "WATCHLIST"
    assert runtime_candidates[0].themes == ()
    assert runtime_mentions[0].themes == (
        "AI Infrastructure",
        "Data Centers",
        "Semiconductors",
    )
    assert report["mapped_news_mentions_available"] is True
    assert report["mapped_news_mention_count"] == 1

    health = FinancialHealth(80, 80, 80, 80, 80, 80, 80)
    row = ThemeEnrichedDiscoveryEngine(paper_trade_mode=True).evaluate(
        runtime_candidates,
        runtime_mentions,
        {"NVDA": health},
        as_of=runtime_mentions[0].mentioned_on,
    )[0]
    assert row.watchlist_status == "WATCHLIST"
    assert "Semiconductors" in row.themes
    assert row.theme_momentum_score > 0


def test_context_only_source_cannot_create_trusted_theme_momentum(tmp_path: Path) -> None:
    path = tmp_path / "mapped_underlying_news_mentions.csv"
    _write_mapped_news(path, source_class="SOCIAL_COMMUNITY")
    mention = mapped_news_mentions(path)[0]

    health = FinancialHealth(80, 80, 80, 80, 80, 80, 80)
    from swing_trade_bot.discovery_engine import CandidateState

    row = ThemeEnrichedDiscoveryEngine(paper_trade_mode=True).evaluate(
        [CandidateState("NVDA", "NVDX", status="WATCHLIST")],
        [mention],
        {"NVDA": health},
        as_of=mention.mentioned_on,
    )[0]
    assert row.themes == ""
    assert row.theme_momentum_score == 0.0

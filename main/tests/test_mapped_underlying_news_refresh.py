from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from swing_trade_bot.mapped_underlying_news_refresh import (
    google_news_rss_url,
    parse_google_news_rss,
    refresh_mapped_underlying_news,
    write_mapped_underlying_news_refresh,
)


def _registry(path: Path) -> Path:
    payload = {
        "schema_version": "2.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "mapping_policy": "EXPLICIT_VERIFIED_ONE_TO_MANY_NO_TICKER_INFERENCE",
        "review_policy": {"cadence": "WEEKLY_WEEKEND", "preferred_vehicle_scope": "FUTURE_NEW_CANDIDATES_ONLY", "existing_positions_unchanged": True, "switch_threshold_points": 5.0},
        "mappings": [
            {"underlying_symbol": "NVDA", "preferred_vehicle": "NVDX", "vehicles": [{"symbol": "NVDX", "verified": True, "enabled": True}]},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _rss(*items: tuple[str, str, str]) -> str:
    body = []
    for title, source, pubdate in items:
        body.append(
            f"<item><title>{title}</title><link>https://example.com/a</link>"
            f"<pubDate>{pubdate}</pubDate><source>{source}</source></item>"
        )
    return "<rss><channel>" + "".join(body) + "</channel></rss>"


def test_google_news_query_targets_underlying_company() -> None:
    url = google_news_rss_url("NVDA")
    assert "NVDA" in url
    assert "Nvidia" in url
    assert "NVDX" not in url


def test_parser_reads_publisher_and_date() -> None:
    rows = parse_google_news_rss(
        _rss(("Nvidia earnings rise", "Reuters", "Mon, 17 Aug 2026 12:00:00 GMT"))
    )
    assert rows[0]["source"] == "Reuters"
    assert rows[0]["mentioned_on"] == date(2026, 8, 17)


def test_refresh_accepts_known_trusted_publishers_and_flags_catalysts(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    xml = _rss(
        ("Nvidia earnings beat expectations", "Reuters", "Mon, 17 Aug 2026 12:00:00 GMT"),
        ("Analyst upgrade raises price target for Nvidia", "Yahoo Finance", "Sun, 16 Aug 2026 12:00:00 GMT"),
    )
    report = refresh_mapped_underlying_news(
        registry_path=registry,
        as_of=date(2026, 8, 18),
        fetch_text=lambda url: xml,
    )
    assert report["accepted_mention_count"] == 2
    assert report["trusted_mention_count"] == 2
    assert report["symbols_with_news"] == 1
    assert {row["source_class"] for row in report["rows"]} == {"INSTITUTIONAL_NEWS", "PROFESSIONAL_RESEARCH"}
    assert any(row["earnings_growth_related"] == "true" for row in report["rows"])
    assert any(row["analyst_upgrade_related"] == "true" for row in report["rows"])
    summary = report["symbol_summaries"][0]
    assert summary["preferred_vehicle"] == "NVDX"
    assert summary["independent_trusted_source_count"] == 2
    assert summary["trusted_sources"] == ["REUTERS", "YAHOO FINANCE"]
    assert report["ai_cio_discovery_status_used_as_evidence"] is False


def test_repeated_articles_from_one_publisher_are_one_independent_source(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    xml = _rss(
        ("Nvidia story one", "Yahoo Finance", "Mon, 17 Aug 2026 12:00:00 GMT"),
        ("Nvidia story two", "Yahoo Finance", "Sun, 16 Aug 2026 12:00:00 GMT"),
        ("Nvidia story three", "Yahoo Finance", "Sat, 15 Aug 2026 12:00:00 GMT"),
    )
    report = refresh_mapped_underlying_news(
        registry_path=registry,
        as_of=date(2026, 8, 18),
        fetch_text=lambda url: xml,
    )
    assert report["trusted_mention_count"] == 3
    summary = report["symbol_summaries"][0]
    assert summary["trusted_mention_count"] == 3
    assert summary["independent_trusted_source_count"] == 1
    assert summary["trusted_sources"] == ["YAHOO FINANCE"]


def test_social_community_is_context_only_not_trusted(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    xml = _rss(("Nvidia chatter", "Stocktwits", "Mon, 17 Aug 2026 12:00:00 GMT"))
    report = refresh_mapped_underlying_news(
        registry_path=registry,
        as_of=date(2026, 8, 18),
        fetch_text=lambda url: xml,
    )
    assert report["accepted_mention_count"] == 1
    assert report["trusted_mention_count"] == 0
    assert report["rejected_or_untrusted_count"] == 1
    assert report["rows"][0]["source_class"] == "SOCIAL_COMMUNITY"
    assert report["rows"][0]["scoring_eligible"] == "false"
    assert report["symbol_summaries"][0]["independent_trusted_source_count"] == 0


def test_unknown_publishers_remain_auditable_but_do_not_become_mentions(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    xml = _rss(("Nvidia rumor", "Random Blog", "Mon, 17 Aug 2026 12:00:00 GMT"))
    report = refresh_mapped_underlying_news(
        registry_path=registry,
        as_of=date(2026, 8, 18),
        fetch_text=lambda url: xml,
    )
    assert report["accepted_mention_count"] == 0
    assert report["rejected_or_untrusted_count"] == 1
    assert any(row.get("publisher") == "Random Blog" and row.get("accepted") is False for row in report["audit"])


def test_stale_mentions_are_not_written(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    xml = _rss(("Old Nvidia story", "Reuters", "Wed, 01 Jul 2026 12:00:00 GMT"))
    report = refresh_mapped_underlying_news(
        registry_path=registry,
        as_of=date(2026, 8, 18),
        fetch_text=lambda url: xml,
    )
    assert report["accepted_mention_count"] == 0
    assert report["trusted_mention_count"] == 0


def test_fetch_failure_is_visible_and_refresh_stays_paper_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "registry.json")
    report = refresh_mapped_underlying_news(
        registry_path=registry,
        as_of=date(2026, 8, 18),
        fetch_text=lambda url: (_ for _ in ()).throw(OSError("network down")),
    )
    assert report["errors"]
    assert report["symbol_summaries"][0]["status"] == "FETCH_OR_PARSE_ERROR"
    assert report["paper_trade_mode"] is True
    assert report["live_trading_enabled"] is False
    assert report["broker_execution_enabled"] is False
    assert report["order_placement_enabled"] is False


def test_write_keeps_swing_news_mentions_separate_from_runtime_intake(tmp_path: Path) -> None:
    payload = {
        "rows": [{
            "underlying_symbol": "NVDA", "source": "Reuters", "original_source": "Reuters",
            "source_class": "INSTITUTIONAL_NEWS", "mentioned_on": "2026-08-17", "themes": "",
            "earnings_growth_related": "true", "analyst_upgrade_related": "false",
            "headline": "Nvidia earnings", "url": "https://example.com/a", "scoring_eligible": "true",
        }],
        "paper_trade_mode": True,
    }
    csv_path, json_path = write_mapped_underlying_news_refresh(payload, output_dir=tmp_path)
    assert csv_path.name == "mapped_underlying_news_mentions.csv"
    assert json_path.name == "mapped_underlying_news_refresh.json"
    assert not (tmp_path / "discovery_mentions_runtime.csv").exists()

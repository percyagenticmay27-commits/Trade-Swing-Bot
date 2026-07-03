import csv
import unittest
import uuid
from datetime import date
from pathlib import Path

from swing_trade_bot.mention_extractor import (
    CSV_COLUMNS,
    RawMentionItem,
    extract_mentions,
    extract_tickers,
    is_approved_source,
    tag_themes,
    write_discovery_mentions_csv,
)
from swing_trade_bot.discovery_engine import load_mentions
from swing_trade_bot.news_adapter import NewsDiscoveryAdapter
from swing_trade_bot.youtube_adapter import YouTubeDiscoveryAdapter


class DiscoveryAdapterTests(unittest.TestCase):
    def test_ticker_extraction_supports_symbols_and_company_names(self) -> None:
        text = "Nebius expands AI infrastructure while Bloom Energy (BE) supports data centers. $NBIS"

        self.assertEqual(extract_tickers(text), {"NBIS", "BE"})

    def test_duplicate_mentions_same_source_same_day_are_ignored(self) -> None:
        items = [
            raw("Bloomberg", "Nebius NBIS adds AI data center capacity"),
            raw("Bloomberg", "NBIS shares rally on data center demand"),
        ]

        mentions = extract_mentions(items)

        self.assertEqual(len([mention for mention in mentions if mention.underlying_symbol == "NBIS"]), 1)

    def test_approved_institutional_source_filtering(self) -> None:
        adapter = NewsDiscoveryAdapter()
        mentions = adapter.collect(
            [
                raw("Reuters", "Iris Energy IREN gains on bitcoin mining expansion"),
                raw("Random Blog", "NBIS mentioned by an unapproved source"),
            ]
        )

        self.assertEqual([mention.underlying_symbol for mention in mentions], ["IREN"])
        self.assertTrue(is_approved_source("Reuters", "INSTITUTIONAL"))
        self.assertFalse(is_approved_source("Random Blog", "INSTITUTIONAL"))

    def test_youtube_source_filtering(self) -> None:
        adapter = YouTubeDiscoveryAdapter()
        mentions = adapter.collect(
            [
                raw("Bow Tie Nation", "NBIS and NEBX AI infrastructure setup", source_type="YOUTUBE"),
                raw("Unknown Channel", "IREN bitcoin mining trade", source_type="YOUTUBE"),
            ]
        )

        self.assertEqual([mention.underlying_symbol for mention in mentions], ["NBIS", "NEBX"])
        self.assertTrue(is_approved_source("Bow Tie Nation", "YOUTUBE"))
        self.assertFalse(is_approved_source("Unknown Channel", "YOUTUBE"))

    def test_theme_tagging(self) -> None:
        tags = tag_themes("AI infrastructure, data centers, semiconductors, and bitcoin mining")

        self.assertEqual(
            tags,
            ("AI Infrastructure", "Data Centers", "Semiconductors", "Bitcoin Mining"),
        )

    def test_csv_output_uses_required_columns(self) -> None:
        with temp_output_path() as path:
            mentions = extract_mentions([raw("Reuters", "NBIS expands AI data center capacity")])
            write_discovery_mentions_csv(path, mentions)
            with path.open(newline="", encoding="utf-8") as input_file:
                rows = list(csv.DictReader(input_file))

        self.assertEqual(tuple(rows[0].keys()), CSV_COLUMNS)
        self.assertEqual(rows[0]["underlying_symbol"], "NBIS")
        self.assertEqual(rows[0]["theme_tags"], "AI Infrastructure;Data Centers")

    def test_adapter_csv_feeds_discovery_engine_loader(self) -> None:
        with temp_output_path() as path:
            mentions = extract_mentions([raw("SEC Filings", "NBIS AI infrastructure filing")])
            write_discovery_mentions_csv(path, mentions)
            loaded = load_mentions(path)

        self.assertEqual(loaded[0].underlying_symbol, "NBIS")
        self.assertEqual(loaded[0].themes, ("AI Infrastructure",))

    def test_adapters_reject_live_mode(self) -> None:
        with self.assertRaises(ValueError):
            NewsDiscoveryAdapter(paper_trade_mode=False)
        with self.assertRaises(ValueError):
            YouTubeDiscoveryAdapter(paper_trade_mode=False)


def raw(
    source: str,
    title: str,
    *,
    source_type: str = "INSTITUTIONAL",
    body: str = "",
) -> RawMentionItem:
    return RawMentionItem(
        source=source,
        title=title,
        url=f"https://example.com/{uuid.uuid4().hex}",
        published_on=date(2026, 6, 24),
        source_type=source_type,
        body=body,
    )


def temp_output_path():
    class TempOutputPath:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"discovery_mentions_{uuid.uuid4().hex}.csv"

        def __enter__(self) -> Path:
            return self.path

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            if self.path.exists():
                self.path.unlink()

    return TempOutputPath()


if __name__ == "__main__":
    unittest.main()

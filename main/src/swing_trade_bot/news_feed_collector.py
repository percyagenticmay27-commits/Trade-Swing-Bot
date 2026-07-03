"""Collect approved institutional news feed rows into paper-only discovery mentions."""

from __future__ import annotations

import argparse
import csv
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from swing_trade_bot.mention_extractor import ExtractedMention, RawMentionItem, write_discovery_mentions_csv
from swing_trade_bot.news_adapter import NewsDiscoveryAdapter


class NewsFeedCollector:
    """Convert approved institutional feed rows into normalized ticker mentions."""

    def __init__(self, *, paper_trade_mode: bool = True) -> None:
        if not paper_trade_mode:
            raise ValueError("NewsFeedCollector requires paper_trade_mode=True")
        self.paper_trade_mode = paper_trade_mode
        self.adapter = NewsDiscoveryAdapter(paper_trade_mode=True)

    def collect(self, items: Iterable[RawMentionItem]) -> list[ExtractedMention]:
        """Extract mentions from provided feed items."""
        return self.adapter.collect(items)

    def collect_from_csv(self, input_path: Path) -> list[ExtractedMention]:
        """Load latest-article feed rows from CSV and extract mentions."""
        return self.collect(load_news_feed_csv(input_path))

    def write_mentions(self, input_path: Path, output_path: Path) -> Path:
        """Write news_mentions.csv."""
        return write_discovery_mentions_csv(output_path, self.collect_from_csv(input_path))


def load_news_feed_csv(path: Path) -> list[RawMentionItem]:
    """Load raw news feed rows.

    Supported columns include source, publish_date/published_on, url, article_text,
    and body. The source_type column is optional and defaults to INSTITUTIONAL.
    """
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        items: list[RawMentionItem] = []
        for row in csv.DictReader(input_file):
            items.append(
                RawMentionItem(
                    source=row["source"],
                    title=row["title"],
                    url=row.get("url", ""),
                    published_on=date.fromisoformat(row.get("publish_date") or row["published_on"]),
                    source_type=row.get("source_type") or "INSTITUTIONAL",
                    body=row.get("article_text") or row.get("body", ""),
                )
            )
        return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect approved institutional news feed mentions")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("news_mentions.csv"))
    args = parser.parse_args()

    path = NewsFeedCollector(paper_trade_mode=True).write_mentions(args.input, args.output)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()

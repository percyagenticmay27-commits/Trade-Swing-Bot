"""Collect approved YouTube feed rows into paper-only discovery mentions."""

from __future__ import annotations

import argparse
import csv
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path

from swing_trade_bot.mention_extractor import ExtractedMention, RawMentionItem, write_discovery_mentions_csv
from swing_trade_bot.youtube_adapter import YouTubeDiscoveryAdapter


TranscriptProvider = Callable[[str], str]


class YouTubeFeedCollector:
    """Convert approved YouTube feed rows into normalized ticker mentions."""

    def __init__(
        self,
        *,
        paper_trade_mode: bool = True,
        transcript_provider: TranscriptProvider | None = None,
    ) -> None:
        if not paper_trade_mode:
            raise ValueError("YouTubeFeedCollector requires paper_trade_mode=True")
        self.paper_trade_mode = paper_trade_mode
        self.transcript_provider = transcript_provider
        self.adapter = YouTubeDiscoveryAdapter(paper_trade_mode=True)

    def collect(self, items: Iterable[RawMentionItem]) -> list[ExtractedMention]:
        """Extract mentions from provided feed items."""
        return self.adapter.collect(items)

    def collect_from_csv(self, input_path: Path) -> list[ExtractedMention]:
        """Load latest-video feed rows from CSV and extract mentions."""
        return self.collect(load_youtube_feed_csv(input_path, transcript_provider=self.transcript_provider))

    def write_mentions(self, input_path: Path, output_path: Path) -> Path:
        """Write youtube_mentions.csv."""
        return write_discovery_mentions_csv(output_path, self.collect_from_csv(input_path))


def load_youtube_feed_csv(
    path: Path,
    *,
    transcript_provider: TranscriptProvider | None = None,
) -> list[RawMentionItem]:
    """Load raw YouTube feed rows.

    Supported columns include channel_name/source, publish_date/published_on,
    video_url/url, description, and optional transcript.
    """
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        items: list[RawMentionItem] = []
        for row in csv.DictReader(input_file):
            url = row.get("video_url") or row.get("url", "")
            transcript = row.get("transcript", "")
            if not transcript and transcript_provider is not None:
                transcript = transcript_provider(url)
            body = "\n".join(value for value in (row.get("description", ""), transcript) if value)
            items.append(
                RawMentionItem(
                    source=row.get("channel_name") or row.get("source", ""),
                    title=row["title"],
                    url=url,
                    published_on=date.fromisoformat(row.get("publish_date") or row["published_on"]),
                    source_type="YOUTUBE",
                    body=body,
                )
            )
        return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect approved YouTube feed mentions")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("youtube_mentions.csv"))
    args = parser.parse_args()

    path = YouTubeFeedCollector(paper_trade_mode=True).write_mentions(args.input, args.output)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()

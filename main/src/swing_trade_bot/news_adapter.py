"""Approved institutional-source discovery adapter.

The adapter is paper/data only. It accepts feed or export rows from approved
sources and writes normalized discovery_mentions.csv records.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

from swing_trade_bot.mention_extractor import (
    ExtractedMention,
    RawMentionItem,
    extract_mentions,
    load_raw_items_csv,
    write_discovery_mentions_csv,
)


class NewsDiscoveryAdapter:
    """Collect institutional mentions from approved source feed records."""

    def __init__(self, *, paper_trade_mode: bool = True) -> None:
        if not paper_trade_mode:
            raise ValueError("NewsDiscoveryAdapter requires paper_trade_mode=True")
        self.paper_trade_mode = paper_trade_mode

    def collect(self, items: Iterable[RawMentionItem]) -> list[ExtractedMention]:
        """Return normalized mentions from approved institutional items only."""
        institutional_items = (
            item
            for item in items
            if item.source_type.strip().upper() in {"INSTITUTIONAL", "NEWS", "SEC", "EARNINGS"}
        )
        return extract_mentions(institutional_items)

    def collect_from_csv(self, input_path: Path) -> list[ExtractedMention]:
        """Load raw news rows from CSV and return extracted mentions."""
        return self.collect(load_raw_items_csv(input_path, default_source_type="INSTITUTIONAL"))

    def write_mentions(self, input_path: Path, output_path: Path) -> Path:
        """Extract mentions from a raw-news CSV and write discovery_mentions.csv."""
        return write_discovery_mentions_csv(output_path, self.collect_from_csv(input_path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract approved institutional discovery mentions")
    parser.add_argument("--input", type=Path, required=True, help="CSV with source,title,url,published_on,body")
    parser.add_argument("--output", type=Path, default=Path("discovery_mentions.csv"))
    args = parser.parse_args()

    path = NewsDiscoveryAdapter(paper_trade_mode=True).write_mentions(args.input, args.output)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()

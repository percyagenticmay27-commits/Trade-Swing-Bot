"""Mention extraction utilities for the paper-only discovery workflow."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from swing_trade_bot.discovery_engine import APPROVED_THEMES


APPROVED_INSTITUTIONAL_SOURCES = {
    "BLOOMBERG",
    "REUTERS",
    "MARKETBEAT",
    "WALLSTREETZEN",
    "SEC FILINGS",
    "SEC FILING",
    "EARNINGS REPORTS",
    "EARNINGS REPORT",
}
APPROVED_YOUTUBE_SOURCES = {
    "BOW TIE NATION",
    "MARKETBEAT YOUTUBE",
    "WALLSTREETZEN YOUTUBE",
    "LET'S TALK MONEY WITH JOSEPH HOGUE",
    "LET'S TALK MONEY",
    "WALL STREET TRAPPER",
    "TICKER SYMBOL YOU",
    "EARN YOUR LEISURE",
}
CSV_COLUMNS = (
    "underlying_symbol",
    "source",
    "mentioned_on",
    "title",
    "url",
    "source_type",
    "theme_tags",
)
SourceType = str


COMPANY_TICKER_ALIASES = {
    "BLOOM ENERGY": "BE",
    "GRANITESHARES 2X LONG NBIS DAILY ETF": "NEBX",
    "IRIS ENERGY": "IREN",
    "IREN": "IREN",
    "NEBIUS": "NBIS",
    "NEBIUS GROUP": "NBIS",
    "NVIDIA": "NVDA",
    "SUPER MICRO COMPUTER": "SMCI",
    "SUPER MICRO": "SMCI",
    "TESLA": "TSLA",
}
TICKER_STOP_WORDS = {
    "AI",
    "API",
    "CEO",
    "CFO",
    "CSV",
    "DCF",
    "DCA",
    "EPS",
    "ETF",
    "EV",
    "GDP",
    "IPO",
    "LLC",
    "NYSE",
    "QQQ",
    "SEC",
    "SPY",
    "THE",
    "USA",
}
THEME_KEYWORDS = {
    "AI Infrastructure": (
        "ai infrastructure",
        "artificial intelligence",
        "gpu cluster",
        "ai data center",
        "accelerator",
    ),
    "Data Centers": ("data center", "datacenter", "colocation"),
    "Semiconductors": ("semiconductor", "chip", "gpu", "dram", "memory"),
    "Nuclear Power": ("nuclear", "uranium", "reactor"),
    "Energy Storage": ("energy storage", "battery storage", "grid storage"),
    "Robotics": ("robotics", "robot", "automation"),
    "Quantum Computing": ("quantum",),
    "Cybersecurity": ("cybersecurity", "cyber security", "security software"),
    "Bitcoin Mining": ("bitcoin mining", "crypto mining", "hash rate", "miner"),
    "Cloud Computing": ("cloud computing", "cloud infrastructure", "hyperscale"),
    "Defense Tech": ("defense tech", "defense", "drone", "military"),
    "Clean Energy": ("clean energy", "renewable", "solar", "wind"),
    "Hydrogen": ("hydrogen", "fuel cell"),
    "Electric Vehicles": ("electric vehicle", "electric vehicles", " ev ", " evs "),
}


@dataclass(frozen=True, slots=True)
class RawMentionItem:
    """One article or video before ticker extraction."""

    source: str
    title: str
    url: str
    published_on: date
    source_type: SourceType
    body: str = ""


@dataclass(frozen=True, slots=True)
class ExtractedMention:
    """One normalized ticker mention ready for discovery_mentions.csv."""

    underlying_symbol: str
    source: str
    mentioned_on: date
    title: str
    url: str
    source_type: SourceType
    theme_tags: tuple[str, ...] = ()


def normalize_ticker(value: str) -> str:
    """Normalize common ticker token formats to uppercase symbols."""
    return re.sub(r"[^A-Z0-9.]", "", value.upper()).strip(".")


def extract_tickers(
    text: str,
    *,
    company_aliases: Mapping[str, str] = COMPANY_TICKER_ALIASES,
) -> set[str]:
    """Extract explicit tickers and known company-name aliases from text."""
    tickers: set[str] = set()
    for match in re.finditer(r"(?:\$|NASDAQ:\s*|NYSE:\s*|NYSEARCA:\s*)([A-Z][A-Z0-9.]{0,5})\b", text):
        tickers.add(normalize_ticker(match.group(1)))
    for match in re.finditer(r"\(([A-Z][A-Z0-9.]{0,5})\)", text):
        symbol = normalize_ticker(match.group(1))
        if symbol not in TICKER_STOP_WORDS:
            tickers.add(symbol)
    for match in re.finditer(r"\b[A-Z]{2,5}\b", text):
        symbol = normalize_ticker(match.group(0))
        if symbol not in TICKER_STOP_WORDS:
            tickers.add(symbol)

    upper_text = text.upper()
    for company, ticker in company_aliases.items():
        if re.search(rf"\b{re.escape(company.upper())}\b", upper_text):
            tickers.add(normalize_ticker(ticker))
    return tickers


def tag_themes(text: str) -> tuple[str, ...]:
    """Return approved theme tags inferred from title/body keywords."""
    padded = f" {text.lower()} "
    tags = [
        theme
        for theme, keywords in THEME_KEYWORDS.items()
        if theme.upper() in APPROVED_THEMES and any(keyword in padded for keyword in keywords)
    ]
    return tuple(tags)


def is_approved_source(source: str, source_type: SourceType) -> bool:
    """Return whether a raw item comes from an approved source list."""
    normalized = _normalize_source(source)
    normalized_type = source_type.strip().upper()
    if normalized_type == "YOUTUBE":
        return normalized in APPROVED_YOUTUBE_SOURCES
    if normalized_type in {"INSTITUTIONAL", "NEWS", "SEC", "EARNINGS"}:
        return normalized in APPROVED_INSTITUTIONAL_SOURCES
    return False


def extract_mentions(items: Iterable[RawMentionItem]) -> list[ExtractedMention]:
    """Extract, normalize, approve, and de-duplicate raw article/video mentions."""
    mentions: list[ExtractedMention] = []
    seen: set[tuple[str, str, date]] = set()
    for item in items:
        if not is_approved_source(item.source, item.source_type):
            continue
        text = f"{item.title}\n{item.body}"
        themes = tag_themes(text)
        for symbol in sorted(extract_tickers(text)):
            key = (symbol, _normalize_source(item.source), item.published_on)
            if key in seen:
                continue
            seen.add(key)
            mentions.append(
                ExtractedMention(
                    underlying_symbol=symbol,
                    source=item.source,
                    mentioned_on=item.published_on,
                    title=item.title,
                    url=item.url,
                    source_type=item.source_type.upper(),
                    theme_tags=themes,
                )
            )
    return mentions


def load_raw_items_csv(path: Path, *, default_source_type: SourceType) -> list[RawMentionItem]:
    """Load raw article/video rows from CSV for offline or API-export workflows."""
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        rows = []
        for row in csv.DictReader(input_file):
            rows.append(
                RawMentionItem(
                    source=row["source"],
                    title=row["title"],
                    url=row.get("url", ""),
                    published_on=date.fromisoformat(row["published_on"]),
                    source_type=row.get("source_type") or default_source_type,
                    body=row.get("body", ""),
                )
            )
        return rows


def write_discovery_mentions_csv(path: Path, mentions: Sequence[ExtractedMention]) -> Path:
    """Write discovery_mentions.csv with the adapter-required schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for mention in mentions:
            writer.writerow(
                {
                    "underlying_symbol": mention.underlying_symbol,
                    "source": mention.source,
                    "mentioned_on": mention.mentioned_on.isoformat(),
                    "title": mention.title,
                    "url": mention.url,
                    "source_type": mention.source_type,
                    "theme_tags": ";".join(mention.theme_tags),
                }
            )
    return path


def read_discovery_mentions_csv(path: Path) -> list[ExtractedMention]:
    """Read a discovery mention CSV created by the adapters."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        mentions: list[ExtractedMention] = []
        for row in csv.DictReader(input_file):
            mentions.append(
                ExtractedMention(
                    underlying_symbol=normalize_ticker(row["underlying_symbol"]),
                    source=row["source"],
                    mentioned_on=date.fromisoformat(row["mentioned_on"]),
                    title=row.get("title", ""),
                    url=row.get("url", ""),
                    source_type=row.get("source_type", "").upper(),
                    theme_tags=_split_values(row.get("theme_tags") or row.get("themes", "")),
                )
            )
        return mentions


def merge_mentions(mentions: Iterable[ExtractedMention]) -> list[ExtractedMention]:
    """Deduplicate mentions by symbol, source, and date while preserving first detail row."""
    merged: list[ExtractedMention] = []
    seen: set[tuple[str, str, date]] = set()
    for mention in mentions:
        key = (
            normalize_ticker(mention.underlying_symbol),
            _normalize_source(mention.source),
            mention.mentioned_on,
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            ExtractedMention(
                underlying_symbol=key[0],
                source=mention.source,
                mentioned_on=mention.mentioned_on,
                title=mention.title,
                url=mention.url,
                source_type=mention.source_type.upper(),
                theme_tags=mention.theme_tags,
            )
        )
    return sorted(merged, key=lambda item: (item.mentioned_on, item.source, item.underlying_symbol))


def _normalize_source(source: str) -> str:
    return source.strip().upper()


def _split_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.replace("|", ";").split(";") if item.strip())

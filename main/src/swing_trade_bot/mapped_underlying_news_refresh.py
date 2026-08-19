"""Read-only news evidence refresh for the persistent Swing mapped universe.

The AI CIO may nominate symbols, but Swing independently refreshes recent source
mentions for every persistent mapped underlying. This collector writes its own
artifact and never overwrites AI CIO/local discovery mentions.

The default provider is Google News RSS used as an aggregator. Trust is granted
only after the article publisher is normalized through Swing's existing source
classification rules. Unknown publishers remain visible in the audit but do not
become trusted scoring evidence.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from .enterprise_evidence_normalization import normalize_enterprise_source, source_class_profile
from .leveraged_vehicle_registry import preferred_vehicle_mapping

MENTIONS_FILENAME = "mapped_underlying_news_mentions.csv"
AUDIT_FILENAME = "mapped_underlying_news_refresh.json"
LOOKBACK_DAYS = 30
MAX_ITEMS_PER_SYMBOL = 25

COMPANY_NAMES: dict[str, str] = {
    "AMZN": "Amazon",
    "AVGO": "Broadcom",
    "GOOGL": "Alphabet Google",
    "NFLX": "Netflix",
    "NVDA": "Nvidia",
    "PLTR": "Palantir",
    "SNDK": "Sandisk SanDisk",
}

TextFetcher = Callable[[str], str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": os.getenv("SWING_HTTP_USER_AGENT", "Trade-Swing-Bot/1.0 read-only research"),
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def google_news_rss_url(symbol: str) -> str:
    company = COMPANY_NAMES.get(symbol.upper(), symbol.upper())
    query = f'({symbol.upper()} OR "{company}") stock when:{LOOKBACK_DAYS}d'
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )


def _parse_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return parsedate_to_datetime(text).date()
    except (TypeError, ValueError, OverflowError):
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def parse_google_news_rss(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    rows: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        source_node = item.find("source")
        publisher = (source_node.text if source_node is not None else "") or ""
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = _parse_date(item.findtext("pubDate") or "")
        if not title or published is None:
            continue
        rows.append(
            {
                "source": publisher.strip(),
                "title": title,
                "url": link,
                "mentioned_on": published,
            }
        )
    return rows


def _catalyst_flags(title: str) -> tuple[bool, bool]:
    text = title.upper()
    earnings = any(token in text for token in ("EARNINGS", "REVENUE", "EPS", "PROFIT", "RESULTS", "GUIDANCE"))
    upgrade = any(token in text for token in ("UPGRADE", "RAISES PRICE TARGET", "PRICE TARGET RAISED", "OUTPERFORM", "OVERWEIGHT"))
    return earnings, upgrade


def refresh_mapped_underlying_news(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    as_of: date | None = None,
    fetch_text: TextFetcher = _fetch_text,
) -> dict[str, Any]:
    mapping = preferred_vehicle_mapping(registry_path)
    today = as_of or date.today()
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    errors: list[str] = []

    for symbol in sorted(mapping):
        url = google_news_rss_url(symbol)
        try:
            items = parse_google_news_rss(fetch_text(url))[:MAX_ITEMS_PER_SYMBOL]
        except Exception as exc:
            errors.append(f"{symbol}:{type(exc).__name__}:{exc}")
            audit.append({
                "underlying_symbol": symbol,
                "preferred_vehicle": mapping[symbol],
                "provider": "GOOGLE_NEWS_RSS",
                "status": "FETCH_OR_PARSE_ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "query_url": url,
            })
            continue

        accepted = 0
        trusted = 0
        seen: set[tuple[str, date, str]] = set()
        for item in items:
            mentioned = item["mentioned_on"]
            age = (today - mentioned).days
            if age < 0 or age > LOOKBACK_DAYS:
                continue
            normalized = normalize_enterprise_source(item.get("source"))
            audit_row = {
                "underlying_symbol": symbol,
                "preferred_vehicle": mapping[symbol],
                "publisher": item.get("source"),
                "title": item.get("title"),
                "url": item.get("url"),
                "mentioned_on": mentioned.isoformat(),
                "age_days": age,
                "accepted": normalized.accepted,
                "source_class": normalized.source_class,
                "normalization_method": normalized.normalization_method,
                "warning": normalized.warning,
            }
            audit.append(audit_row)
            if not normalized.accepted or not normalized.source_class:
                continue
            identity = (normalized.original_source.upper(), mentioned, str(item.get("title", "")).upper())
            if identity in seen:
                continue
            seen.add(identity)
            profile = source_class_profile(normalized.source_class)
            earnings, upgrade = _catalyst_flags(str(item.get("title", "")))
            rows.append({
                "underlying_symbol": symbol,
                "source": normalized.original_source,
                "original_source": normalized.original_source,
                "source_class": normalized.source_class,
                "mentioned_on": mentioned.isoformat(),
                "themes": "",
                "earnings_growth_related": str(earnings).lower(),
                "analyst_upgrade_related": str(upgrade).lower(),
                "headline": item.get("title", ""),
                "url": item.get("url", ""),
            })
            accepted += 1
            if profile is not None and profile.weight > 0:
                trusted += 1
        audit.append({
            "underlying_symbol": symbol,
            "preferred_vehicle": mapping[symbol],
            "provider": "GOOGLE_NEWS_RSS",
            "status": "AVAILABLE",
            "items_seen": len(items),
            "accepted_mentions": accepted,
            "trusted_mentions": trusted,
            "query_url": url,
        })

    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "generated_at_utc": _utc_now(),
        "as_of": today.isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "provider": "GOOGLE_NEWS_RSS",
        "mapped_underlying_count": len(mapping),
        "accepted_mention_count": len(rows),
        "rows": rows,
        "audit": audit,
        "errors": errors,
        "ai_cio_discovery_status_used_as_evidence": False,
    }


def write_mapped_underlying_news_refresh(payload: Mapping[str, Any], *, output_dir: str | Path = "results") -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / MENTIONS_FILENAME
    json_path = root / AUDIT_FILENAME

    fields = (
        "underlying_symbol", "source", "original_source", "source_class", "mentioned_on",
        "themes", "earnings_growth_related", "analyst_upgrade_related", "headline", "url",
    )
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False, dir=root) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in payload.get("rows", []):
            writer.writerow({field: row.get(field, "") for field in fields})
        handle.flush()
        os.fsync(handle.fileno())
        temp_csv = Path(handle.name)
    os.replace(temp_csv, csv_path)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=root) as handle:
        json.dump(dict(payload), handle, indent=2, default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temp_json = Path(handle.name)
    os.replace(temp_json, json_path)
    return csv_path, json_path


def build_and_write_mapped_underlying_news_refresh(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    output_dir: str | Path = "results",
    as_of: date | None = None,
) -> dict[str, Any]:
    payload = refresh_mapped_underlying_news(registry_path=registry_path, as_of=as_of)
    write_mapped_underlying_news_refresh(payload, output_dir=output_dir)
    return payload


if __name__ == "__main__":
    report = build_and_write_mapped_underlying_news_refresh()
    print(
        "Mapped underlying news refresh: "
        f"{report['mapped_underlying_count']} mapped; "
        f"{report['accepted_mention_count']} accepted mentions; "
        f"{len(report['errors'])} errors"
    )

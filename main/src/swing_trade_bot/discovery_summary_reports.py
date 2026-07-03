"""Standalone theme momentum and source confluence report writers."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ThemeMomentumRow:
    theme: str
    symbol_count: int
    average_theme_momentum_score: float
    top_symbols: str


@dataclass(frozen=True, slots=True)
class SourceConfluenceRow:
    source_confluence_level: str
    symbol_count: int
    top_symbols: str


def build_discovery_summary_reports(watchlist_path: Path, output_dir: Path, *, paper_trade_mode: bool = True) -> tuple[list[ThemeMomentumRow], list[SourceConfluenceRow]]:
    """Read watchlist_report CSV/JSON and write theme/source summary JSON files."""
    if not paper_trade_mode:
        raise ValueError("Discovery summary reports require paper_trade_mode=True")
    rows = _read_watchlist_rows(watchlist_path)
    theme_rows = _theme_rows(rows)
    confluence_rows = _confluence_rows(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "theme_momentum.json").write_text(json.dumps({"paper_trade_mode": True, "rows": [asdict(row) for row in theme_rows]}, indent=2) + "\n", encoding="utf-8")
    (output_dir / "source_confluence.json").write_text(json.dumps({"paper_trade_mode": True, "rows": [asdict(row) for row in confluence_rows]}, indent=2) + "\n", encoding="utf-8")
    return theme_rows, confluence_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Create paper-only discovery summary reports")
    parser.add_argument("--watchlist", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    args = parser.parse_args()
    build_discovery_summary_reports(args.watchlist, args.output_dir, paper_trade_mode=True)


def _read_watchlist_rows(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows", payload if isinstance(payload, list) else [])
        return rows if isinstance(rows, list) else []
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return list(csv.DictReader(input_file))


def _theme_rows(rows: list[dict[str, object]]) -> list[ThemeMomentumRow]:
    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        themes = [theme.strip() for theme in str(row.get("themes", "Unclassified")).replace("|", ";").split(";") if theme.strip()]
        for theme in themes or ["Unclassified"]:
            buckets[theme].append(row)
    output = []
    for theme, items in buckets.items():
        scores = [_float(item.get("theme_momentum_score")) for item in items]
        top_symbols = sorted(str(item.get("underlying_symbol", item.get("symbol", ""))).upper() for item in items if item.get("underlying_symbol") or item.get("symbol"))[:10]
        output.append(ThemeMomentumRow(theme, len(items), round(sum(scores) / len(scores), 6) if scores else 0.0, ";".join(top_symbols)))
    return sorted(output, key=lambda row: (-row.average_theme_momentum_score, row.theme))


def _confluence_rows(rows: list[dict[str, object]]) -> list[SourceConfluenceRow]:
    counts = Counter(str(row.get("source_confluence_level", "UNKNOWN")).upper() for row in rows)
    output = []
    for level, count in counts.items():
        top_symbols = sorted(str(row.get("underlying_symbol", row.get("symbol", ""))).upper() for row in rows if str(row.get("source_confluence_level", "UNKNOWN")).upper() == level)[:10]
        output.append(SourceConfluenceRow(level, count, ";".join(top_symbols)))
    return sorted(output, key=lambda row: (-row.symbol_count, row.source_confluence_level))


def _float(value: object) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    return float(value)


if __name__ == "__main__":
    main()

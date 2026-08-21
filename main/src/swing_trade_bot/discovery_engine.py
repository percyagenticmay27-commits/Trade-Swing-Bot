"""Paper-only discovery scoring and watchlist lifecycle management."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, cast

from .enterprise_evidence_normalization import source_class_profile


WatchlistStatus = Literal["DISCOVERY", "MONITOR", "WATCHLIST", "LOW", "MEDIUM", "HIGH", "REMOVED"]
CapacityStatus = Literal["ACTIVE", "OVER_CAPACITY_MONITOR", "REMOVED"]

WATCHLIST_MAX = 20
HIGH_PRIORITY_WATCHLIST_MAX = 10
APPROVED_THEMES = {
    "AI INFRASTRUCTURE",
    "DATA CENTERS",
    "SEMICONDUCTORS",
    "NUCLEAR POWER",
    "ENERGY STORAGE",
    "ROBOTICS",
    "QUANTUM COMPUTING",
    "CYBERSECURITY",
    "BITCOIN MINING",
    "CLOUD COMPUTING",
    "DEFENSE TECH",
    "CLEAN ENERGY",
    "HYDROGEN",
    "ELECTRIC VEHICLES",
}

SOURCE_WEIGHTS = {
    "BLOOMBERG": 3,
    "REUTERS": 3,
    "SEC FILING": 3,
    "SEC FILINGS": 3,
    "EARNINGS REPORT": 3,
    "EARNINGS REPORTS": 3,
    "MARKETBEAT": 2,
    "WALLSTREETZEN": 2,
    "BOW TIE NATION": 1,
    "LET'S TALK MONEY": 1,
    "LET'S TALK MONEY WITH JOSEPH HOGUE": 1,
    "WALL STREET TRAPPER": 1,
    "TICKER SYMBOL YOU": 1,
    "EARN YOUR LEISURE": 1,
}
INSTITUTIONAL_SOURCES = {
    "BLOOMBERG",
    "REUTERS",
    "MARKETBEAT",
    "WALLSTREETZEN",
    "SEC FILING",
    "SEC FILINGS",
    "EARNINGS REPORT",
    "EARNINGS REPORTS",
}
YOUTUBE_SOURCES = {
    "BOW TIE NATION",
    "MARKETBEAT YOUTUBE",
    "WALLSTREETZEN YOUTUBE",
    "LET'S TALK MONEY",
    "LET'S TALK MONEY WITH JOSEPH HOGUE",
    "WALL STREET TRAPPER",
    "TICKER SYMBOL YOU",
    "EARN YOUR LEISURE",
}
YOUTUBE_ALIASES = {
    "MARKETBEAT YOUTUBE": "MARKETBEAT",
    "WALLSTREETZEN YOUTUBE": "WALLSTREETZEN",
}
FINANCIAL_FIELDS = (
    "revenue_growth",
    "eps_growth",
    "operating_cash_flow",
    "gross_margin_trend",
    "debt_health",
    "analyst_revisions",
    "sector_strength",
)
PAPER_ACCOUNT_VALUE = 100.0


@dataclass(frozen=True, slots=True)
class SourceMention:
    """One dated candidate mention from an independent source.

    source_class/original_source are optional Enterprise adapter metadata. Legacy
    Swing CSV rows omit them and retain the historical literal-source semantics.
    """

    underlying_symbol: str
    source: str
    mentioned_on: date
    themes: tuple[str, ...] = ()
    earnings_growth_related: bool = False
    analyst_upgrade_related: bool = False
    source_class: str | None = None
    original_source: str | None = None


@dataclass(frozen=True, slots=True)
class FinancialHealth:
    """Seven equally weighted financial health components, each from 0 to 100."""

    revenue_growth: float
    eps_growth: float
    operating_cash_flow: float
    gross_margin_trend: float
    debt_health: float
    analyst_revisions: float
    sector_strength: float

    @property
    def score(self) -> float:
        values = [getattr(self, field) for field in FINANCIAL_FIELDS]
        if any(value < 0 or value > 100 for value in values):
            raise ValueError("financial health components must be between 0 and 100")
        return sum(values) / len(values)


@dataclass(frozen=True, slots=True)
class CandidateState:
    """Current paper lifecycle state and performance metrics."""

    underlying_symbol: str
    leveraged_symbol: str | None
    status: WatchlistStatus = "DISCOVERY"
    paper_return: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    number_of_trades: int = 0
    trading_days: int = 0
    days_in_status: int = 0
    earnings_stability_score: float = 50.0
    leveraged_vehicle_exists: bool = True
    themes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WatchlistRow:
    """Requested watchlist report fields plus lifecycle decision metadata."""

    underlying_symbol: str
    leveraged_symbol: str
    source_count: int
    institutional_source_count: int
    youtube_source_count: int
    source_confluence_score: int
    source_confluence_level: str
    financial_health_score: float
    watchlist_status: WatchlistStatus
    paper_return: float
    win_rate: float
    profit_factor: float
    trading_days: int
    promotion_eligible: bool
    themes: str = ""
    theme_momentum_score: float = 0.0
    composite_score: float = 0.0
    watchlist_rank: int | None = None
    high_priority_rank: int | None = None
    capacity_status: CapacityStatus = "ACTIVE"


class DiscoveryEngine:
    """Score candidates and manage a simulated $100 watchlist lifecycle."""

    def __init__(self, *, paper_trade_mode: bool = True, paper_account_value: float = PAPER_ACCOUNT_VALUE) -> None:
        if not paper_trade_mode:
            raise ValueError("Discovery engine requires paper_trade_mode=True")
        if paper_account_value <= 0:
            raise ValueError("paper_account_value must be positive")
        self.paper_trade_mode = paper_trade_mode
        self.paper_account_value = paper_account_value

    def evaluate(
        self,
        candidates: Sequence[CandidateState],
        mentions: Sequence[SourceMention],
        financial_health: Mapping[str, FinancialHealth],
        *,
        as_of: date,
    ) -> list[WatchlistRow]:
        """Evaluate every candidate using rolling 30-day source evidence."""
        rows = [
            self._evaluate_candidate(candidate, mentions, financial_health, as_of)
            for candidate in candidates
        ]
        return _apply_watchlist_capacity(rows)

    def _evaluate_candidate(
        self,
        candidate: CandidateState,
        mentions: Sequence[SourceMention],
        financial_health: Mapping[str, FinancialHealth],
        as_of: date,
    ) -> WatchlistRow:
        symbol = candidate.underlying_symbol.upper()
        recent = _recent_mentions(symbol, mentions, as_of)
        independent_mentions = _independent_scoring_mentions(recent)
        source_count = len(independent_mentions)
        institutional_count = sum(_mention_is_institutional(item, recent) for item in independent_mentions)
        youtube_count = sum(_mention_is_youtube_or_creator(item, recent) for item in independent_mentions)
        confluence = sum(_mention_weight(item, recent) for item in independent_mentions)
        health = financial_health.get(symbol)
        health_score = health.score if health is not None else 0.0
        momentum_score = theme_momentum_score(candidate.themes, recent, as_of=as_of)
        status = self._next_status(
            candidate,
            source_count=source_count,
            confluence=confluence,
            financial_health_score=health_score,
        )
        row = WatchlistRow(
            underlying_symbol=symbol,
            leveraged_symbol=(candidate.leveraged_symbol or "").upper(),
            source_count=source_count,
            institutional_source_count=institutional_count,
            youtube_source_count=youtube_count,
            source_confluence_score=confluence,
            source_confluence_level=confluence_level(confluence, source_count),
            financial_health_score=round(health_score, 2),
            watchlist_status=status,
            paper_return=candidate.paper_return,
            win_rate=candidate.win_rate,
            profit_factor=candidate.profit_factor,
            trading_days=candidate.trading_days,
            promotion_eligible=_promotion_eligible(candidate, confluence, health_score),
            themes=";".join(candidate.themes),
            theme_momentum_score=momentum_score,
            capacity_status="REMOVED" if status == "REMOVED" else "ACTIVE",
        )
        return replace(
            row,
            composite_score=round(composite_score(row, candidate.earnings_stability_score), 2),
        )

    @staticmethod
    def _next_status(
        candidate: CandidateState,
        *,
        source_count: int,
        confluence: int,
        financial_health_score: float,
    ) -> WatchlistStatus:
        if candidate.status == "LOW":
            if candidate.days_in_status < 90:
                return "LOW"
            if (
                candidate.win_rate < 35.0
                or candidate.profit_factor < 1.25
                or financial_health_score < 60.0
                or not candidate.leveraged_vehicle_exists
            ):
                return "WATCHLIST"
            return "LOW"
        if not candidate.leveraged_symbol or not candidate.leveraged_vehicle_exists:
            return "REMOVED"
        if candidate.status == "WATCHLIST":
            if _promotion_eligible(candidate, confluence, financial_health_score):
                return "LOW"
            if candidate.days_in_status >= 90 and (
                source_count < 2 or confluence <= 2 or financial_health_score < 60.0
            ):
                return "MONITOR"
            return "WATCHLIST"
        if candidate.status == "MEDIUM":
            return "LOW" if candidate.win_rate < 35.0 or candidate.profit_factor < 1.25 else "MEDIUM"
        if candidate.status == "HIGH":
            return "MEDIUM" if candidate.win_rate < 45.0 or candidate.profit_factor < 1.50 else "HIGH"
        if source_count < 2 or confluence <= 2:
            return "DISCOVERY"
        if confluence <= 4 or financial_health_score < 70.0:
            return "MONITOR"
        return "WATCHLIST"


def composite_score(row: WatchlistRow, earnings_stability_score: float) -> float:
    """Return the LOW replacement composite score on a 0-100 scale."""
    if not 0 <= earnings_stability_score <= 100:
        raise ValueError("earnings_stability_score must be between 0 and 100")
    paper_score = _paper_trading_score(row.paper_return, row.win_rate, row.profit_factor)
    confluence_score = min(row.source_confluence_score / 7.0 * 100.0, 100.0)
    return (
        0.35 * paper_score
        + 0.25 * row.financial_health_score
        + 0.20 * confluence_score
        + 0.10 * row.theme_momentum_score
        + 0.10 * earnings_stability_score
    )


def theme_momentum_score(
    themes: Sequence[str],
    mentions: Sequence[SourceMention],
    *,
    as_of: date,
) -> float:
    """Score approved-theme breadth, acceleration, institutional support, and catalysts."""
    normalized_themes = [
        theme.strip().upper()
        for theme in themes
        if theme.strip().upper() in APPROVED_THEMES
    ]
    if not normalized_themes:
        return 0.0

    scores: list[float] = []
    recent_cutoff = as_of - timedelta(days=15)
    prior_cutoff = as_of - timedelta(days=30)
    for theme in normalized_themes:
        relevant = [
            item
            for item in mentions
            if theme in {_normalize_theme(value) for value in item.themes}
            and prior_cutoff <= item.mentioned_on <= as_of
            and _mention_weight(item, mentions) > 0
        ]
        independent = _independent_scoring_mentions(relevant)
        current_mentions = sum(item.mentioned_on >= recent_cutoff for item in relevant)
        prior_mentions = len(relevant) - current_mentions

        breadth = min(len(independent) / 4.0, 1.0) * 35.0
        institutional_support = min(
            sum(_mention_is_institutional(item, relevant) for item in independent) / 3.0,
            1.0,
        ) * 25.0
        if current_mentions == 0:
            trend = 0.0
        elif prior_mentions == 0:
            trend = 25.0 if current_mentions >= 2 else 12.5
        else:
            growth = (current_mentions - prior_mentions) / prior_mentions
            trend = max(0.0, min(25.0, 12.5 + growth * 12.5))
        catalyst = (
            7.5 * any(item.earnings_growth_related for item in relevant)
            + 7.5 * any(item.analyst_upgrade_related for item in relevant)
        )
        scores.append(breadth + institutional_support + trend + catalyst)
    return round(sum(scores) / len(scores), 2)


def confluence_level(score: int, source_count: int) -> str:
    """Translate weighted rolling mentions into the requested confluence level."""
    if source_count < 2 or score <= 2:
        return "IGNORE"
    if score <= 4:
        return "MONITOR"
    if score <= 6:
        return "WATCHLIST"
    return "HIGH_PRIORITY_WATCHLIST"


def can_replace_low(
    candidate: WatchlistRow,
    current_low: WatchlistRow,
    *,
    candidate_earnings_stability: float,
    current_earnings_stability: float,
    current_low_days: int,
) -> bool:
    """Return whether a watchlist candidate can replace an eligible LOW member."""
    if current_low_days < 90 or candidate.watchlist_status != "WATCHLIST":
        return False
    return (
        composite_score(candidate, candidate_earnings_stability)
        >= composite_score(current_low, current_earnings_stability) + 15.0
    )


def write_watchlist_reports(output_dir: Path, rows: Sequence[WatchlistRow]) -> tuple[Path, Path]:
    """Write watchlist_report.csv and watchlist_report.json."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "watchlist_report.csv"
    json_path = output_dir / "watchlist_report.json"
    fieldnames = list(WatchlistRow.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    json_path.write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "paper_account_value": PAPER_ACCOUNT_VALUE,
                "rolling_mention_days": 30,
                "minimum_independent_sources": 2,
                "watchlist_max": WATCHLIST_MAX,
                "high_priority_watchlist_max": HIGH_PRIORITY_WATCHLIST_MAX,
                "theme_momentum_scale": "0-100",
                "rows": [asdict(row) for row in rows],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return csv_path, json_path


def load_candidates(path: Path) -> list[CandidateState]:
    """Load candidate state rows from CSV."""
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return [
            CandidateState(
                underlying_symbol=row["underlying_symbol"],
                leveraged_symbol=row.get("leveraged_symbol") or None,
                status=cast(WatchlistStatus, row.get("status", "DISCOVERY").upper()),
                paper_return=float(row.get("paper_return", 0)),
                win_rate=float(row.get("win_rate", 0)),
                profit_factor=float(row.get("profit_factor", 0)),
                number_of_trades=int(row.get("number_of_trades", 0)),
                trading_days=int(row.get("trading_days", 0)),
                days_in_status=int(row.get("days_in_status", 0)),
                earnings_stability_score=float(row.get("earnings_stability_score", 50)),
                leveraged_vehicle_exists=_bool(row.get("leveraged_vehicle_exists", "true")),
                themes=_split_values(row.get("themes", "")),
            )
            for row in csv.DictReader(input_file)
        ]


def load_mentions(path: Path) -> list[SourceMention]:
    """Load dated discovery mentions from CSV."""
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return [
            SourceMention(
                underlying_symbol=row["underlying_symbol"],
                source=row["source"],
                mentioned_on=date.fromisoformat(row["mentioned_on"]),
                themes=_split_values(row.get("themes") or row.get("theme_tags", "")),
                earnings_growth_related=_bool(row.get("earnings_growth_related", "false")),
                analyst_upgrade_related=_bool(row.get("analyst_upgrade_related", "false")),
                source_class=(row.get("source_class") or "").strip().upper() or None,
                original_source=(row.get("original_source") or "").strip() or None,
            )
            for row in csv.DictReader(input_file)
        ]


def load_financial_health(path: Path) -> dict[str, FinancialHealth]:
    """Load financial component scores from CSV."""
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return {
            row["underlying_symbol"].upper(): FinancialHealth(
                **{field: float(row[field]) for field in FINANCIAL_FIELDS}
            )
            for row in csv.DictReader(input_file)
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the paper discovery and watchlist lifecycle engine")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--mentions", type=Path, required=True)
    parser.add_argument("--financial-health", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    rows = DiscoveryEngine(paper_trade_mode=True).evaluate(
        load_candidates(args.candidates),
        load_mentions(args.mentions),
        load_financial_health(args.financial_health),
        as_of=args.as_of,
    )
    write_watchlist_reports(args.output_dir, rows)
    print(format_watchlist_table(rows))


def format_watchlist_table(rows: Sequence[WatchlistRow]) -> str:
    headers = ("Underlying", "Leveraged", "Level", "Theme", "Composite", "WL Rank", "HP Rank", "Capacity", "Status")
    values = [
        (
            row.underlying_symbol,
            row.leveraged_symbol or "-",
            row.source_confluence_level,
            f"{row.theme_momentum_score:.1f}",
            f"{row.composite_score:.1f}",
            str(row.watchlist_rank or "-"),
            str(row.high_priority_rank or "-"),
            row.capacity_status,
            row.watchlist_status,
        )
        for row in rows
    ]
    widths = [max(len(headers[index]), *(len(row[index]) for row in values)) for index in range(len(headers))]
    lines = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in values)
    return "\n".join(lines)


def _recent_mentions(symbol: str, mentions: Iterable[SourceMention], as_of: date) -> list[SourceMention]:
    cutoff = as_of - timedelta(days=30)
    return [
        mention
        for mention in mentions
        if mention.underlying_symbol.upper() == symbol and cutoff <= mention.mentioned_on <= as_of
    ]


def _normalize_source(source: str) -> str:
    return source.strip().upper()


def _mention_identity(mention: SourceMention) -> str:
    return _normalize_source(mention.original_source or mention.source)


def _mention_weight(mention: SourceMention, mentions: Sequence[SourceMention]) -> int:
    if mention.source_class is not None:
        profile = source_class_profile(mention.source_class)
        return profile.weight if profile is not None else 0
    return _source_weight(_normalize_source(mention.source), mentions)


def _mention_is_institutional(mention: SourceMention, mentions: Sequence[SourceMention]) -> bool:
    if mention.source_class is not None:
        profile = source_class_profile(mention.source_class)
        return bool(profile and profile.institutional and profile.weight > 0)
    return _normalize_source(mention.source) in INSTITUTIONAL_SOURCES


def _mention_is_youtube_or_creator(mention: SourceMention, mentions: Sequence[SourceMention]) -> bool:
    if mention.source_class is not None:
        profile = source_class_profile(mention.source_class)
        return bool(profile and profile.youtube_or_creator and profile.weight > 0)
    return _is_youtube_source(_normalize_source(mention.source), mentions)


def _independent_scoring_mentions(mentions: Sequence[SourceMention]) -> list[SourceMention]:
    """Deduplicate trusted evidence by actual source identity.

    Legacy mentions preserve historical behavior, including source breadth even when
    a legacy literal has no configured weight. Enterprise mentions with source_class
    metadata must have a recognized positive-weight class to contribute to trusted
    breadth/confluence. SOCIAL_COMMUNITY and unrecognized Enterprise evidence remain
    visible in runtime evidence but cannot inflate trusted source counts.
    """
    result: dict[str, SourceMention] = {}
    for mention in mentions:
        if mention.source_class is not None and _mention_weight(mention, mentions) <= 0:
            continue
        result.setdefault(_mention_identity(mention), mention)
    return list(result.values())


def _source_weight(source: str, mentions: Sequence[SourceMention]) -> int:
    if source in YOUTUBE_ALIASES:
        return 1
    if source in SOURCE_WEIGHTS:
        return SOURCE_WEIGHTS[source]
    return 1 if _is_youtube_source(source, mentions) else 0


def _is_youtube_source(source: str, mentions: Sequence[SourceMention]) -> bool:
    if source in YOUTUBE_SOURCES:
        return True
    return any(_normalize_source(item.source) == source and "YOUTUBE" in item.source.upper() for item in mentions)


def _promotion_eligible(candidate: CandidateState, confluence: int, financial_health_score: float) -> bool:
    return (
        candidate.status == "WATCHLIST"
        and candidate.trading_days >= 90
        and candidate.number_of_trades >= 10
        and candidate.win_rate >= 40.0
        and candidate.profit_factor >= 1.50
        and financial_health_score >= 70.0
        and confluence >= 5
        and bool(candidate.leveraged_symbol)
        and candidate.leveraged_vehicle_exists
    )


def _paper_trading_score(paper_return: float, win_rate: float, profit_factor: float) -> float:
    return max(
        0.0,
        min(
            100.0,
            0.40 * max(0.0, min(win_rate, 100.0))
            + 0.35 * max(0.0, min(profit_factor / 2.0 * 100.0, 100.0))
            + 0.25 * max(0.0, min(50.0 + paper_return, 100.0)),
        ),
    )


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _split_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.replace("|", ";").split(";") if item.strip())


def _normalize_theme(theme: str) -> str:
    return theme.strip().upper()


def _apply_watchlist_capacity(rows: Sequence[WatchlistRow]) -> list[WatchlistRow]:
    high_priority = sorted(
        (
            row
            for row in rows
            if row.watchlist_status == "WATCHLIST"
            and row.source_confluence_level == "HIGH_PRIORITY_WATCHLIST"
        ),
        key=lambda row: (-row.composite_score, row.underlying_symbol),
    )
    standard = sorted(
        (
            row
            for row in rows
            if row.watchlist_status == "WATCHLIST"
            and row.source_confluence_level != "HIGH_PRIORITY_WATCHLIST"
        ),
        key=lambda row: (-row.composite_score, row.underlying_symbol),
    )
    high_ranks = {row.underlying_symbol: rank for rank, row in enumerate(high_priority, 1)}
    standard_ranks = {row.underlying_symbol: rank for rank, row in enumerate(standard, 1)}

    ranked_rows: list[WatchlistRow] = []
    for row in rows:
        high_rank = high_ranks.get(row.underlying_symbol)
        watchlist_rank = standard_ranks.get(row.underlying_symbol)
        over_capacity = (
            high_rank is not None and high_rank > HIGH_PRIORITY_WATCHLIST_MAX
        ) or (
            watchlist_rank is not None and watchlist_rank > WATCHLIST_MAX
        )
        capacity_status: CapacityStatus
        if row.watchlist_status == "REMOVED":
            capacity_status = "REMOVED"
        elif over_capacity:
            capacity_status = "OVER_CAPACITY_MONITOR"
        else:
            capacity_status = "ACTIVE"
        ranked_rows.append(
            replace(
                row,
                watchlist_rank=watchlist_rank,
                high_priority_rank=high_rank,
                capacity_status=capacity_status,
            )
        )
    return ranked_rows


if __name__ == "__main__":
    main()

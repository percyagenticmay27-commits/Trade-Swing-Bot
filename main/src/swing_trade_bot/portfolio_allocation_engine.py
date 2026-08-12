"""Portfolio allocation engine for paper-only monthly rebalance recommendations.

Rank is used to determine how much capital or percentage allocation each eligible
opportunity receives, not merely which opportunity receives capital first.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path


STRATEGY_ID = "SWING-001"
LEVEL_CAPS = {
    "HIGH": 0.25,
    "MEDIUM": 0.15,
    "LOW": 0.07,
    "WATCHLIST": 0.0,
}
MAX_POSITION_ALLOCATION = 0.25
CASH_EQUIVALENT_SYMBOL = "SGOV"
PORTFOLIO_COLUMNS = (
    "symbol",
    "confidence_level",
    "active_strategy",
    "rank",
    "allocation_percent",
    "theme",
    "theme_allocation",
    "cash_equivalent",
)


@dataclass(frozen=True, slots=True)
class PortfolioCandidate:
    """Inputs needed to allocate one symbol."""

    symbol: str
    confidence_level: str
    active_strategy: str
    rank: int | None
    theme: str
    strategy_return: float = 0.0


@dataclass(frozen=True, slots=True)
class PortfolioAllocationRow:
    """One portfolio allocation recommendation row."""

    symbol: str
    confidence_level: str
    active_strategy: str
    rank: int | None
    allocation_percent: float
    theme: str
    theme_allocation: float
    cash_equivalent: str


@dataclass(frozen=True, slots=True)
class PortfolioAllocationReport:
    """Full monthly rebalance recommendation."""

    rows: tuple[PortfolioAllocationRow, ...]
    cash_allocation: float
    sgov_allocation: float
    paper_trade_mode: bool = True


class PortfolioAllocationEngine:
    """Allocate portfolio percentages from confidence, rank, and strategy performance."""

    def __init__(self, *, paper_trade_mode: bool = True) -> None:
        if not paper_trade_mode:
            raise ValueError("Portfolio allocation requires paper_trade_mode=True")
        self.paper_trade_mode = paper_trade_mode

    def allocate(self, candidates: Sequence[PortfolioCandidate]) -> PortfolioAllocationReport:
        """Return capped allocation percentages plus SGOV reserve.

        Better opportunity rank increases the raw allocation weight, subject to
        confidence and paper-only position caps.
        """
        live_candidates = [
            candidate
            for candidate in candidates
            if _normalize_level(candidate.confidence_level) != "WATCHLIST"
        ]
        ordered = sorted(
            live_candidates,
            key=lambda candidate: (
                _rank_value(candidate.rank),
                candidate.symbol,
            ),
        )
        raw_weights = _raw_rank_weights(ordered)
        capped_rows: list[PortfolioAllocationRow] = []

        for candidate, raw_weight in zip(ordered, raw_weights):
            level = _normalize_level(candidate.confidence_level)
            cap = min(LEVEL_CAPS[level], MAX_POSITION_ALLOCATION)
            theme = candidate.theme or "Unclassified"
            allocation = min(raw_weight, cap)
            capped_rows.append(
                PortfolioAllocationRow(
                    symbol=candidate.symbol.upper(),
                    confidence_level=level,
                    active_strategy=candidate.active_strategy,
                    rank=candidate.rank,
                    allocation_percent=round(allocation * 100.0, 6),
                    theme=theme,
                    theme_allocation=0.0,
                    cash_equivalent="",
                )
            )

        theme_totals: dict[str, float] = defaultdict(float)
        for row in capped_rows:
            theme_totals[row.theme] += row.allocation_percent
        rows_with_theme_totals = tuple(
            replace(row, theme_allocation=round(theme_totals[row.theme], 6))
            for row in capped_rows
        )
        allocated = sum(row.allocation_percent for row in rows_with_theme_totals) / 100.0
        reserve = max(0.0, 1.0 - allocated)
        return PortfolioAllocationReport(
            rows=rows_with_theme_totals,
            cash_allocation=round(reserve * 100.0, 6),
            sgov_allocation=round(reserve * 100.0, 6),
        )


def build_portfolio_allocation_report(
    *,
    confidence_path: Path,
    watchlist_path: Path,
    strategy_recommendations_path: Path,
    output_dir: Path,
    paper_trade_mode: bool = True,
) -> PortfolioAllocationReport:
    """Read current reports, allocate, and write portfolio allocation files."""
    if not paper_trade_mode:
        raise ValueError("Portfolio allocation requires paper_trade_mode=True")
    candidates = build_candidates(
        confidence_rows=read_confidence_rows(confidence_path),
        watchlist_rows=read_watchlist_rows(watchlist_path),
        strategy_rows=read_strategy_rows(strategy_recommendations_path),
    )
    report = PortfolioAllocationEngine(paper_trade_mode=True).allocate(candidates)
    write_portfolio_reports(output_dir, report)
    return report


def build_candidates(
    *,
    confidence_rows: Mapping[str, dict[str, str]],
    watchlist_rows: Mapping[str, dict[str, str]],
    strategy_rows: Mapping[str, dict[str, str]],
) -> list[PortfolioCandidate]:
    """Combine confidence, watchlist, and strategy rows into allocator inputs."""
    symbols = sorted(set(confidence_rows) | set(watchlist_rows) | set(strategy_rows))
    candidates: list[PortfolioCandidate] = []
    for symbol in symbols:
        confidence = confidence_rows.get(symbol, {}).get("confidence", "")
        watchlist = watchlist_rows.get(symbol, {})
        strategy = strategy_rows.get(symbol, {})
        if not confidence:
            status = watchlist.get("watchlist_status", "WATCHLIST").upper()
            confidence = status if status in LEVEL_CAPS else "WATCHLIST"
        rank = _parse_rank(watchlist.get("watchlist_rank") or watchlist.get("high_priority_rank"))
        candidates.append(
            PortfolioCandidate(
                symbol=symbol,
                confidence_level=confidence,
                active_strategy=strategy.get("active_strategy", "Strategy A"),
                rank=rank,
                theme=_primary_theme(watchlist.get("themes", "")),
                strategy_return=_strategy_return(strategy),
            )
        )
    return candidates


def write_portfolio_reports(output_dir: Path, report: PortfolioAllocationReport) -> tuple[Path, Path]:
    """Atomically write portfolio_allocations.csv and portfolio_allocations.json."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "portfolio_allocations.csv"
    json_path = output_dir / "portfolio_allocations.json"
    rows = [
        *[asdict(row) for row in report.rows],
        {
            "symbol": CASH_EQUIVALENT_SYMBOL,
            "confidence_level": "RESERVE",
            "active_strategy": "",
            "rank": "",
            "allocation_percent": report.sgov_allocation,
            "theme": "Cash Equivalent",
            "theme_allocation": report.sgov_allocation,
            "cash_equivalent": CASH_EQUIVALENT_SYMBOL,
        },
    ]
    _atomic_csv(csv_path, list(PORTFOLIO_COLUMNS), rows)
    _atomic_json(
        json_path,
        {
            "strategy_id": STRATEGY_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "paper_trade_mode": True,
            "advisory_only": True,
            "live_trading_enabled": False,
            "broker_execution_enabled": False,
            "order_placement_enabled": False,
            "capital_movement_enabled": False,
            "monthly_rebalance": True,
            "max_position_allocation": MAX_POSITION_ALLOCATION,
            "rank_controls_relative_allocation": True,
            "theme_allocation_limit_enabled": False,
            "strategy_assignment_boost_enabled": False,
            "historical_return_weighting_enabled": False,
            "cash_allocation": report.cash_allocation,
            "sgov_allocation": report.sgov_allocation,
            "allocations": rows,
        },
    )
    return csv_path, json_path


def _atomic_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(dict(payload), output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def format_portfolio_table(report: PortfolioAllocationReport) -> str:
    """Render a readable rebalance table."""
    headers = ("Symbol", "Level", "Strategy", "Rank", "Allocation", "Theme", "Theme Total", "Reserve")
    rows = [
        (
            row.symbol,
            row.confidence_level,
            row.active_strategy,
            "-" if row.rank is None else str(row.rank),
            f"{row.allocation_percent:.2f}%",
            row.theme,
            f"{row.theme_allocation:.2f}%",
            row.cash_equivalent or "-",
        )
        for row in report.rows
    ]
    rows.append((CASH_EQUIVALENT_SYMBOL, "RESERVE", "-", "-", f"{report.sgov_allocation:.2f}%", "Cash Equivalent", f"{report.sgov_allocation:.2f}%", CASH_EQUIVALENT_SYMBOL))
    widths = [max(len(headers[index]), *(len(row[index]) for row in rows)) for index in range(len(headers))]
    lines = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows)
    return "\n".join(lines)


def read_confidence_rows(path: Path) -> dict[str, dict[str, str]]:
    return _read_by_symbol(path, "symbol")


def read_watchlist_rows(path: Path) -> dict[str, dict[str, str]]:
    return _read_by_symbol(path, "underlying_symbol")


def read_strategy_rows(path: Path) -> dict[str, dict[str, str]]:
    return _read_by_symbol(path, "symbol")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create paper-only portfolio allocation recommendations")
    parser.add_argument("--confidence", type=Path, required=True)
    parser.add_argument("--watchlist", type=Path, required=True)
    parser.add_argument("--strategies", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    args = parser.parse_args()

    report = build_portfolio_allocation_report(
        confidence_path=args.confidence,
        watchlist_path=args.watchlist,
        strategy_recommendations_path=args.strategies,
        output_dir=args.output_dir,
        paper_trade_mode=True,
    )
    print(format_portfolio_table(report))


def _read_by_symbol(path: Path, symbol_field: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        rows: dict[str, dict[str, str]] = {}
        for row in csv.DictReader(input_file):
            symbol = row[symbol_field].strip().upper()
            rows[symbol] = {key: value for key, value in row.items()}
        return rows


def _raw_rank_weights(candidates: Sequence[PortfolioCandidate]) -> list[float]:
    if not candidates:
        return []
    scores = [
        1.0 / _rank_value(candidate.rank)
        for candidate in candidates
    ]
    total = sum(scores)
    return [score / total for score in scores]


def _strategy_return(row: Mapping[str, str]) -> float:
    active = row.get("active_strategy", "Strategy A").strip().upper()
    key = "strategy_b_return" if active == "STRATEGY B" else "strategy_a_return"
    return _float(row.get(key, "0"))


def _rank_value(rank: int | None) -> int:
    return rank if rank is not None and rank > 0 else 999


def _parse_rank(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    return int(float(value))


def _primary_theme(value: str) -> str:
    themes = [theme.strip() for theme in value.replace("|", ";").split(";") if theme.strip()]
    return themes[0] if themes else "Unclassified"


def _normalize_level(value: str) -> str:
    level = value.strip().upper()
    if level not in LEVEL_CAPS:
        return "WATCHLIST"
    return level


def _float(value: str | None) -> float:
    if value is None or value == "":
        return 0.0
    if value.strip().upper() == "INFINITY":
        return 1_000_000.0
    return float(value)


if __name__ == "__main__":
    main()

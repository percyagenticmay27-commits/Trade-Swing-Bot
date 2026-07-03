import json
import unittest
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

from swing_trade_bot.discovery_engine import (
    CandidateState,
    DiscoveryEngine,
    FinancialHealth,
    SourceMention,
    WatchlistRow,
    can_replace_low,
    composite_score,
    confluence_level,
    theme_momentum_score,
    write_watchlist_reports,
)


AS_OF = date(2026, 6, 23)


class DiscoveryEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DiscoveryEngine()
        self.healthy = {"NBIS": health(80.0)}

    def test_source_confluence_uses_unique_sources_in_rolling_thirty_days(self) -> None:
        mentions = [
            mention("NBIS", "Bloomberg", 5),
            mention("NBIS", "Bloomberg", 10),
            mention("NBIS", "Reuters", 15),
            mention("NBIS", "SEC Filing", 31),
        ]

        row = self.engine.evaluate(
            [candidate()],
            mentions,
            self.healthy,
            as_of=AS_OF,
        )[0]

        self.assertEqual(row.source_count, 2)
        self.assertEqual(row.institutional_source_count, 2)
        self.assertEqual(row.youtube_source_count, 0)
        self.assertEqual(row.source_confluence_score, 6)
        self.assertEqual(row.source_confluence_level, "WATCHLIST")
        self.assertEqual(row.watchlist_status, "WATCHLIST")

    def test_minimum_two_independent_sources_is_enforced(self) -> None:
        row = self.engine.evaluate(
            [candidate()],
            [mention("NBIS", "Bloomberg", 1)],
            self.healthy,
            as_of=AS_OF,
        )[0]

        self.assertEqual(row.source_confluence_score, 3)
        self.assertEqual(row.source_confluence_level, "IGNORE")
        self.assertEqual(row.watchlist_status, "DISCOVERY")

    def test_high_priority_confluence_and_youtube_weighting(self) -> None:
        mentions = [
            mention("NBIS", "Bloomberg", 1),
            mention("NBIS", "Reuters", 2),
            mention("NBIS", "Bow Tie Nation", 3),
        ]

        row = self.engine.evaluate([candidate()], mentions, self.healthy, as_of=AS_OF)[0]

        self.assertEqual(row.source_confluence_score, 7)
        self.assertEqual(row.source_confluence_level, "HIGH_PRIORITY_WATCHLIST")
        self.assertEqual(row.youtube_source_count, 1)
        self.assertEqual(row.watchlist_status, "WATCHLIST")

    def test_financial_health_below_seventy_remains_monitor(self) -> None:
        row = self.engine.evaluate(
            [candidate()],
            [mention("NBIS", "Bloomberg", 1), mention("NBIS", "Reuters", 2)],
            {"NBIS": health(69.0)},
            as_of=AS_OF,
        )[0]

        self.assertEqual(row.watchlist_status, "MONITOR")

    def test_candidate_without_leveraged_vehicle_is_removed(self) -> None:
        row = self.engine.evaluate(
            [candidate(leveraged_symbol=None, leveraged_vehicle_exists=False)],
            [mention("NBIS", "Bloomberg", 1), mention("NBIS", "Reuters", 2)],
            self.healthy,
            as_of=AS_OF,
        )[0]

        self.assertEqual(row.watchlist_status, "REMOVED")

    def test_watchlist_promotes_to_low_after_all_thresholds(self) -> None:
        state = candidate(
            status="WATCHLIST",
            trading_days=90,
            number_of_trades=10,
            win_rate=40.0,
            profit_factor=1.50,
        )
        row = self.engine.evaluate(
            [state],
            [mention("NBIS", "Bloomberg", 1), mention("NBIS", "Reuters", 2)],
            self.healthy,
            as_of=AS_OF,
        )[0]

        self.assertTrue(row.promotion_eligible)
        self.assertEqual(row.watchlist_status, "LOW")

    def test_low_cannot_demote_before_ninety_day_stay(self) -> None:
        state = candidate(
            status="LOW",
            days_in_status=89,
            win_rate=10.0,
            profit_factor=0.5,
        )
        row = self.engine.evaluate([state], [], {"NBIS": health(40.0)}, as_of=AS_OF)[0]

        self.assertEqual(row.watchlist_status, "LOW")

    def test_low_demotes_to_watchlist_after_review(self) -> None:
        state = candidate(
            status="LOW",
            days_in_status=90,
            win_rate=34.9,
            profit_factor=1.5,
        )
        row = self.engine.evaluate([state], [], self.healthy, as_of=AS_OF)[0]

        self.assertEqual(row.watchlist_status, "WATCHLIST")

    def test_existing_medium_and_high_demotion_rules_are_applied(self) -> None:
        candidates = [
            candidate(status="MEDIUM", win_rate=34.0, profit_factor=2.0),
            candidate(
                underlying_symbol="ABC",
                leveraged_symbol="ABCX",
                status="HIGH",
                win_rate=50.0,
                profit_factor=1.49,
            ),
        ]
        rows = self.engine.evaluate(
            candidates,
            [],
            {"NBIS": self.healthy["NBIS"], "ABC": health(80.0)},
            as_of=AS_OF,
        )

        self.assertEqual(rows[0].watchlist_status, "LOW")
        self.assertEqual(rows[1].watchlist_status, "MEDIUM")

    def test_low_replacement_requires_ninety_days_and_fifteen_point_advantage(self) -> None:
        candidate_row = report_row(
            status="WATCHLIST",
            paper_return=30.0,
            win_rate=70.0,
            profit_factor=2.5,
            health=90.0,
            confluence=7,
        )
        low_row = report_row(
            status="LOW",
            paper_return=-10.0,
            win_rate=35.0,
            profit_factor=1.25,
            health=65.0,
            confluence=5,
        )

        self.assertFalse(
            can_replace_low(
                candidate_row,
                low_row,
                candidate_earnings_stability=90,
                current_earnings_stability=50,
                current_low_days=89,
            )
        )
        self.assertTrue(
            can_replace_low(
                candidate_row,
                low_row,
                candidate_earnings_stability=90,
                current_earnings_stability=50,
                current_low_days=90,
            )
        )

    def test_reports_are_written_in_paper_mode(self) -> None:
        with temp_data_dir() as directory:
            row = report_row(status="WATCHLIST")
            csv_path, json_path = write_watchlist_reports(Path(directory), [row])
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertTrue(csv_path.name.endswith(".csv"))
        self.assertTrue(payload["paper_trade_mode"])
        self.assertEqual(payload["paper_account_value"], 100.0)
        self.assertEqual(payload["rows"][0]["underlying_symbol"], "NBIS")
        self.assertIn("theme_momentum_score", payload["rows"][0])
        self.assertIn("composite_score", payload["rows"][0])
        self.assertIn("capacity_status", payload["rows"][0])

    def test_live_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DiscoveryEngine(paper_trade_mode=False)

    def test_confluence_boundaries(self) -> None:
        self.assertEqual(confluence_level(2, 2), "IGNORE")
        self.assertEqual(confluence_level(3, 2), "MONITOR")
        self.assertEqual(confluence_level(5, 2), "WATCHLIST")
        self.assertEqual(confluence_level(7, 2), "HIGH_PRIORITY_WATCHLIST")

    def test_theme_momentum_rewards_breadth_trend_institutions_and_catalysts(self) -> None:
        mentions = [
            themed_mention("NBIS", "Bloomberg", 25, "AI Infrastructure"),
            themed_mention("NBIS", "Reuters", 12, "AI Infrastructure", earnings=True),
            themed_mention("NBIS", "SEC Filing", 8, "AI Infrastructure"),
            themed_mention("NBIS", "Bow Tie Nation", 2, "AI Infrastructure", upgrade=True),
        ]

        score = theme_momentum_score(("AI Infrastructure",), mentions, as_of=AS_OF)

        self.assertEqual(score, 100.0)

    def test_composite_score_uses_new_weights(self) -> None:
        row = report_row(
            status="WATCHLIST",
            paper_return=50.0,
            win_rate=100.0,
            profit_factor=2.0,
            health=100.0,
            confluence=7,
            theme_momentum=100.0,
        )

        self.assertEqual(composite_score(row, 100.0), 100.0)

    def test_watchlist_capacity_max_twenty_and_ranks_by_composite(self) -> None:
        candidates, mentions, financials = qualifying_candidates(21, high_priority=False)

        rows = self.engine.evaluate(candidates, mentions, financials, as_of=AS_OF)
        active = [row for row in rows if row.capacity_status == "ACTIVE"]
        overflow = [row for row in rows if row.capacity_status == "OVER_CAPACITY_MONITOR"]

        self.assertEqual(len(active), 20)
        self.assertEqual(len(overflow), 1)
        self.assertEqual(overflow[0].watchlist_rank, 21)
        ranked = sorted(rows, key=lambda row: row.watchlist_rank or 0)
        self.assertGreaterEqual(ranked[0].composite_score, ranked[-1].composite_score)

    def test_high_priority_capacity_max_ten_and_ranks_separately(self) -> None:
        high_candidates, high_mentions, high_financials = qualifying_candidates(11, high_priority=True)
        standard_candidates, standard_mentions, standard_financials = qualifying_candidates(
            2,
            high_priority=False,
            symbol_prefix="STD",
        )

        rows = self.engine.evaluate(
            high_candidates + standard_candidates,
            high_mentions + standard_mentions,
            high_financials | standard_financials,
            as_of=AS_OF,
        )
        high_rows = [row for row in rows if row.high_priority_rank is not None]
        standard_rows = [row for row in rows if row.watchlist_rank is not None]

        self.assertEqual(sum(row.capacity_status == "ACTIVE" for row in high_rows), 10)
        self.assertEqual(sum(row.capacity_status == "OVER_CAPACITY_MONITOR" for row in high_rows), 1)
        self.assertEqual(sum(row.capacity_status == "ACTIVE" for row in standard_rows), 2)
        self.assertTrue(all(row.high_priority_rank is None for row in standard_rows))

    def test_removed_candidate_has_removed_capacity_status(self) -> None:
        row = self.engine.evaluate(
            [candidate(leveraged_symbol=None, leveraged_vehicle_exists=False)],
            [],
            self.healthy,
            as_of=AS_OF,
        )[0]

        self.assertEqual(row.capacity_status, "REMOVED")


def candidate(**overrides: object) -> CandidateState:
    values: dict[str, object] = {
        "underlying_symbol": "NBIS",
        "leveraged_symbol": "NEBX",
    }
    values.update(overrides)
    return CandidateState(**values)


def mention(symbol: str, source: str, days_ago: int) -> SourceMention:
    return SourceMention(symbol, source, AS_OF - timedelta(days=days_ago))


def themed_mention(
    symbol: str,
    source: str,
    days_ago: int,
    theme: str,
    *,
    earnings: bool = False,
    upgrade: bool = False,
) -> SourceMention:
    return SourceMention(
        symbol,
        source,
        AS_OF - timedelta(days=days_ago),
        (theme,),
        earnings,
        upgrade,
    )


def health(value: float) -> FinancialHealth:
    return FinancialHealth(value, value, value, value, value, value, value)


def report_row(
    *,
    status: str,
    paper_return: float = 10.0,
    win_rate: float = 50.0,
    profit_factor: float = 1.75,
    health: float = 80.0,
    confluence: int = 6,
    theme_momentum: float = 0.0,
) -> WatchlistRow:
    return WatchlistRow(
        underlying_symbol="NBIS",
        leveraged_symbol="NEBX",
        source_count=2,
        institutional_source_count=2,
        youtube_source_count=0,
        source_confluence_score=confluence,
        source_confluence_level=confluence_level(confluence, 2),
        financial_health_score=health,
        watchlist_status=status,
        paper_return=paper_return,
        win_rate=win_rate,
        profit_factor=profit_factor,
        trading_days=100,
        promotion_eligible=False,
        themes="AI Infrastructure",
        theme_momentum_score=theme_momentum,
    )


def qualifying_candidates(
    count: int,
    *,
    high_priority: bool,
    symbol_prefix: str = "SYM",
) -> tuple[list[CandidateState], list[SourceMention], dict[str, FinancialHealth]]:
    candidates: list[CandidateState] = []
    mentions: list[SourceMention] = []
    financials: dict[str, FinancialHealth] = {}
    for index in range(count):
        symbol = f"{symbol_prefix}{index:02d}"
        candidates.append(
            CandidateState(
                underlying_symbol=symbol,
                leveraged_symbol=f"{symbol}X",
                paper_return=float(count - index),
                themes=("AI Infrastructure",),
            )
        )
        mentions.extend(
            [
                themed_mention(symbol, "Bloomberg", 10, "AI Infrastructure"),
                themed_mention(symbol, "Reuters", 5, "AI Infrastructure"),
            ]
        )
        if high_priority:
            mentions.append(themed_mention(symbol, "Bow Tie Nation", 2, "AI Infrastructure"))
        financials[symbol] = health(90.0 - index)
    return candidates, mentions, financials


def temp_data_dir() -> Iterator[str]:
    class TempDataDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"discovery_engine_test_{uuid.uuid4().hex}"

        def __enter__(self) -> str:
            self.path.mkdir()
            return str(self.path)

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for child in self.path.iterdir():
                child.unlink()
            self.path.rmdir()

    return TempDataDir()


if __name__ == "__main__":
    unittest.main()

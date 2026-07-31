import csv
import json
import unittest
import uuid
from pathlib import Path

from swing_trade_bot.portfolio_allocation_engine import (
    PortfolioAllocationEngine,
    PortfolioCandidate,
    build_candidates,
    format_portfolio_table,
    write_portfolio_reports,
)


class PortfolioAllocationEngineTests(unittest.TestCase):
    def test_confidence_caps_and_sgov_reserve_are_applied(self) -> None:
        report = PortfolioAllocationEngine().allocate(
            [
                candidate("SOXL", "HIGH", 1, "Semiconductors"),
                candidate("TQQQ", "MEDIUM", 2, "Cloud Computing"),
                candidate("IONL", "LOW", 3, "Semiconductors"),
            ]
        )
        weights = {row.symbol: row.allocation_percent for row in report.rows}

        self.assertLessEqual(weights["SOXL"], 25.0)
        self.assertLessEqual(weights["TQQQ"], 15.0)
        self.assertLessEqual(weights["IONL"], 7.0)
        self.assertGreater(report.sgov_allocation, 0.0)

    def test_watchlist_is_paper_only_and_not_allocated(self) -> None:
        report = PortfolioAllocationEngine().allocate(
            [
                candidate("NBIS", "WATCHLIST", 1, "AI Infrastructure"),
                candidate("SOXL", "HIGH", 2, "Semiconductors"),
            ]
        )

        self.assertNotIn("NBIS", {row.symbol for row in report.rows})
        self.assertGreater(report.sgov_allocation, 0.0)

    def test_strategy_b_and_historical_return_do_not_boost_allocation(self) -> None:
        report = PortfolioAllocationEngine().allocate(
            [
                candidate("A", "LOW", 1, "AI Infrastructure", strategy="Strategy B", strategy_return=500.0),
                candidate("B", "LOW", 1, "Cloud Computing", strategy="Strategy A", strategy_return=-50.0),
            ]
        )
        weights = {row.symbol: row.allocation_percent for row in report.rows}

        self.assertEqual(weights["A"], weights["B"])
        self.assertLessEqual(weights["A"], 7.0)

    def test_rank_weighting_prefers_rank_one(self) -> None:
        report = PortfolioAllocationEngine().allocate(
            [
                candidate("A", "HIGH", 1, "Theme A"),
                candidate("B", "HIGH", 2, "Theme B"),
                candidate("C", "HIGH", 3, "Theme C"),
                candidate("D", "HIGH", 4, "Theme D"),
                candidate("E", "HIGH", 5, "Theme E"),
                candidate("F", "HIGH", 6, "Theme F"),
                candidate("G", "HIGH", 7, "Theme G"),
                candidate("H", "HIGH", 8, "Theme H"),
                candidate("I", "HIGH", 9, "Theme I"),
                candidate("J", "HIGH", 10, "Theme J"),
            ]
        )
        weights = {row.symbol: row.allocation_percent for row in report.rows}

        self.assertGreater(weights["A"], weights["B"])
        self.assertGreater(weights["B"], weights["C"])

    def test_theme_does_not_reduce_rank_driven_allocation(self) -> None:
        report = PortfolioAllocationEngine().allocate(
            [
                candidate("NBIS", "HIGH", 1, "AI Infrastructure"),
                candidate("NEBX", "HIGH", 2, "AI Infrastructure"),
                candidate("SMCI", "HIGH", 3, "AI Infrastructure"),
                candidate("TQQQ", "HIGH", 4, "Cloud Computing"),
            ]
        )

        weights = {row.symbol: row.allocation_percent for row in report.rows}
        ai_rows = [row for row in report.rows if row.theme == "AI Infrastructure"]
        self.assertGreater(weights["NBIS"], weights["NEBX"])
        self.assertGreater(weights["NEBX"], weights["SMCI"])
        self.assertGreater(ai_rows[0].theme_allocation, 40.0)

    def test_build_candidates_combines_confidence_watchlist_and_strategy_files(self) -> None:
        rows = build_candidates(
            confidence_rows={"SOXL": {"confidence": "HIGH"}},
            watchlist_rows={"SOXL": {"themes": "Semiconductors", "watchlist_rank": "2"}},
            strategy_rows={"SOXL": {"active_strategy": "Strategy B", "strategy_b_return": "22.5"}},
        )

        self.assertEqual(rows[0].confidence_level, "HIGH")
        self.assertEqual(rows[0].active_strategy, "Strategy B")
        self.assertEqual(rows[0].rank, 2)
        self.assertEqual(rows[0].theme, "Semiconductors")
        self.assertEqual(rows[0].strategy_return, 22.5)

    def test_report_files_are_written(self) -> None:
        with workspace_temp_dir() as directory:
            report = PortfolioAllocationEngine().allocate(
                [candidate("SOXL", "HIGH", 1, "Semiconductors")]
            )
            csv_path, json_path = write_portfolio_reports(directory, report)
            with csv_path.open(newline="", encoding="utf-8") as input_file:
                rows = list(csv.DictReader(input_file))
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(rows[-1]["symbol"], "SGOV")
        self.assertTrue(payload["paper_trade_mode"])
        self.assertIn("sgov_allocation", payload)
        self.assertTrue(payload["rank_controls_relative_allocation"])
        self.assertFalse(payload["theme_allocation_limit_enabled"])
        self.assertFalse(payload["strategy_assignment_boost_enabled"])
        self.assertFalse(payload["historical_return_weighting_enabled"])

    def test_rebalance_table_includes_reserve(self) -> None:
        report = PortfolioAllocationEngine().allocate([candidate("SOXL", "HIGH", 1, "Semiconductors")])

        self.assertIn("SGOV", format_portfolio_table(report))

    def test_live_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PortfolioAllocationEngine(paper_trade_mode=False)


def candidate(
    symbol: str,
    confidence: str,
    rank: int,
    theme: str,
    *,
    strategy: str = "Strategy A",
    strategy_return: float = 10.0,
) -> PortfolioCandidate:
    return PortfolioCandidate(
        symbol=symbol,
        confidence_level=confidence,
        active_strategy=strategy,
        rank=rank,
        theme=theme,
        strategy_return=strategy_return,
    )


def workspace_temp_dir():
    class WorkspaceTempDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"portfolio_allocation_test_{uuid.uuid4().hex}"

        def __enter__(self) -> Path:
            self.path.mkdir()
            return self.path

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for child in self.path.iterdir():
                child.unlink()
            self.path.rmdir()

    return WorkspaceTempDir()


if __name__ == "__main__":
    unittest.main()

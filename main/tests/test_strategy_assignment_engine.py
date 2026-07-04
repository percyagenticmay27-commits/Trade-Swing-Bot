import csv
import json
import unittest
from pathlib import Path

from swing_trade_bot.strategy_assignment_engine import (
    STRATEGY_A,
    STRATEGY_B,
    WINDOW_1_WEEK,
    WINDOW_4_WEEK,
    WINDOW_8_WEEK,
    WINDOW_12_WEEK,
    StrategyAssignmentPolicy,
    StrategyPerformanceWindow,
    assign_strategies,
    format_strategy_assignments_markdown,
    load_strategy_performance_windows,
    write_strategy_assignment_outputs,
)


class StrategyAssignmentEngineTests(unittest.TestCase):
    def test_one_week_evidence_is_warning_only(self) -> None:
        assignments = assign_strategies(
            [
                perf("SOXL", WINDOW_1_WEEK, STRATEGY_A, total_return=0, drawdown=5, trades=2),
                perf("SOXL", WINDOW_1_WEEK, STRATEGY_B, total_return=20, drawdown=5, trades=2),
            ],
            active_strategies={"SOXL": STRATEGY_A},
        )

        assignment = assignments[0]
        self.assertFalse(assignment.switch_eligible)
        self.assertEqual(assignment.recommended_strategy, STRATEGY_A)
        self.assertEqual(assignment.confidence_level, "warning")

    def test_four_week_window_can_switch_when_evidence_is_strong(self) -> None:
        assignments = assign_strategies(
            [
                perf("SOXL", WINDOW_4_WEEK, STRATEGY_A, total_return=5, drawdown=8, profit_factor=1.2, trades=5),
                perf("SOXL", WINDOW_4_WEEK, STRATEGY_B, total_return=10, drawdown=9, profit_factor=1.3, trades=5),
            ],
            active_strategies={"SOXL": STRATEGY_A},
        )

        assignment = assignments[0]
        self.assertTrue(assignment.switch_eligible)
        self.assertEqual(assignment.recommended_strategy, STRATEGY_B)
        self.assertEqual(assignment.confidence_level, "review")

    def test_eight_and_twelve_week_windows_have_higher_confidence(self) -> None:
        eight_week = assign_strategies(
            [
                perf("TQQQ", WINDOW_8_WEEK, STRATEGY_A, total_return=3, trades=8),
                perf("TQQQ", WINDOW_8_WEEK, STRATEGY_B, total_return=8, trades=8),
            ],
            active_strategies={"TQQQ": STRATEGY_A},
        )[0]
        twelve_week = assign_strategies(
            [
                perf("AMDL", WINDOW_12_WEEK, STRATEGY_A, total_return=4, trades=12),
                perf("AMDL", WINDOW_12_WEEK, STRATEGY_B, total_return=10, trades=12),
            ],
            active_strategies={"AMDL": STRATEGY_A},
        )[0]

        self.assertEqual(eight_week.confidence_level, "preferred")
        self.assertEqual(twelve_week.confidence_level, "high")

    def test_cooldown_blocks_strategy_change(self) -> None:
        assignment = assign_strategies(
            [
                perf("SOXL", WINDOW_8_WEEK, STRATEGY_A, total_return=0, trades=8),
                perf("SOXL", WINDOW_8_WEEK, STRATEGY_B, total_return=20, trades=8),
            ],
            active_strategies={"SOXL": STRATEGY_A},
            weeks_since_last_switch={"SOXL": 2},
        )[0]

        self.assertFalse(assignment.switch_eligible)
        self.assertEqual(assignment.recommended_strategy, STRATEGY_A)
        self.assertEqual(assignment.cooldown_remaining_weeks, 2)

    def test_drawdown_penalty_can_block_strategy_change(self) -> None:
        assignment = assign_strategies(
            [
                perf("SOXL", WINDOW_8_WEEK, STRATEGY_A, total_return=5, drawdown=5, trades=8),
                perf("SOXL", WINDOW_8_WEEK, STRATEGY_B, total_return=12, drawdown=20, trades=8),
            ],
            active_strategies={"SOXL": STRATEGY_A},
        )[0]

        self.assertFalse(assignment.switch_eligible)
        self.assertEqual(assignment.recommended_strategy, STRATEGY_A)

    def test_profit_factor_rule_can_block_strategy_change(self) -> None:
        assignment = assign_strategies(
            [
                perf("BEX", WINDOW_8_WEEK, STRATEGY_A, total_return=5, profit_factor=2.0, trades=8),
                perf("BEX", WINDOW_8_WEEK, STRATEGY_B, total_return=12, profit_factor=1.0, trades=8),
            ],
            active_strategies={"BEX": STRATEGY_A},
        )[0]

        self.assertFalse(assignment.switch_eligible)

    def test_selects_most_mature_available_window(self) -> None:
        assignment = assign_strategies(
            [
                perf("AMD", WINDOW_4_WEEK, STRATEGY_A, total_return=1, trades=4),
                perf("AMD", WINDOW_4_WEEK, STRATEGY_B, total_return=20, trades=4),
                perf("AMD", WINDOW_12_WEEK, STRATEGY_A, total_return=10, trades=12),
                perf("AMD", WINDOW_12_WEEK, STRATEGY_B, total_return=1, trades=12),
            ],
            active_strategies={"AMD": STRATEGY_A},
        )[0]

        self.assertEqual(assignment.review_window, WINDOW_12_WEEK)
        self.assertEqual(assignment.recommended_strategy, STRATEGY_A)

    def test_policy_requires_paper_mode(self) -> None:
        with self.assertRaises(ValueError):
            StrategyAssignmentPolicy(paper_trade_mode=False)

    def test_output_files_are_written(self) -> None:
        assignments = assign_strategies(
            [
                perf("AMD", WINDOW_8_WEEK, STRATEGY_A, total_return=12, trades=8),
                perf("AMD", WINDOW_8_WEEK, STRATEGY_B, total_return=8, trades=8),
            ]
        )
        output_dir = Path(self._testMethodName)
        try:
            csv_path, json_path, md_path = write_strategy_assignment_outputs(output_dir, assignments)
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["paper_trade_mode"])
            self.assertEqual(payload["assignments"][0]["symbol"], "AMD")
        finally:
            for path in output_dir.glob("*"):
                path.unlink()
            output_dir.rmdir()

    def test_markdown_contains_assignment_table(self) -> None:
        assignment = assign_strategies(
            [
                perf("AMD", WINDOW_8_WEEK, STRATEGY_A, total_return=12, trades=8),
                perf("AMD", WINDOW_8_WEEK, STRATEGY_B, total_return=8, trades=8),
            ]
        )[0]

        markdown = format_strategy_assignments_markdown([assignment])
        self.assertIn("# Strategy Assignment Report", markdown)
        self.assertIn("| AMD |", markdown)

    def test_loads_performance_windows_from_csv(self) -> None:
        path = Path(f"{self._testMethodName}.csv")
        try:
            with path.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(
                    output,
                    fieldnames=[
                        "symbol",
                        "window",
                        "strategy",
                        "total_return",
                        "max_drawdown",
                        "win_rate",
                        "profit_factor",
                        "trade_count",
                        "reentry_success_rate",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "symbol": "amd",
                        "window": WINDOW_4_WEEK,
                        "strategy": STRATEGY_A,
                        "total_return": "5",
                        "max_drawdown": "6",
                        "win_rate": "55",
                        "profit_factor": "1.5",
                        "trade_count": "4",
                        "reentry_success_rate": "",
                    }
                )
            records = load_strategy_performance_windows(path)
            self.assertEqual(records[0].symbol, "AMD")
            self.assertIsNone(records[0].reentry_success_rate)
        finally:
            if path.exists():
                path.unlink()


def perf(
    symbol: str,
    window: str,
    strategy: str,
    *,
    total_return: float,
    drawdown: float = 5.0,
    win_rate: float = 55.0,
    profit_factor: float = 1.5,
    trades: int = 4,
) -> StrategyPerformanceWindow:
    return StrategyPerformanceWindow(
        symbol=symbol,
        window=window,
        strategy=strategy,
        total_return=total_return,
        max_drawdown=drawdown,
        win_rate=win_rate,
        profit_factor=profit_factor,
        trade_count=trades,
    )


if __name__ == "__main__":
    unittest.main()

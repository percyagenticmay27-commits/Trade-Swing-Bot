import json
import unittest
from pathlib import Path

from swing_trade_bot.exit_review_manager import (
    STRATEGY_A,
    STRATEGY_B,
    ExitReviewInput,
    ExitReviewPolicy,
    format_exit_review_markdown,
    review_exit,
    review_exits,
    write_exit_review_outputs,
)


class ExitReviewManagerTests(unittest.TestCase):
    def test_strategy_a_drawdown_alone_continues(self) -> None:
        result = review_exit(
            ExitReviewInput(
                symbol="AMDL",
                active_strategy=STRATEGY_A,
                lifecycle_state="paper_position",
                opportunity_quality_score=85,
                opportunity_quality_trend=-2,
                market_regime_score=65,
                thesis_intact=True,
                unrealized_percent=-12,
            )
        )
        self.assertEqual(result.outcome, "continue_holding")

    def test_strategy_b_drawdown_moves_to_reentry_review(self) -> None:
        result = review_exit(
            ExitReviewInput(
                symbol="AMDL",
                active_strategy=STRATEGY_B,
                lifecycle_state="paper_position",
                opportunity_quality_score=85,
                opportunity_quality_trend=-2,
                market_regime_score=65,
                thesis_intact=True,
                unrealized_percent=-10.5,
            )
        )
        self.assertEqual(result.outcome, "strategy_b_reentry_review")
        self.assertEqual(result.suggested_review_action, "perform_reentry_review")

    def test_thesis_break_has_priority(self) -> None:
        result = review_exit(
            ExitReviewInput("AMD", STRATEGY_A, "paper_position", 88, 0, 70, False)
        )
        self.assertEqual(result.outcome, "thesis_broken_review")

    def test_giveback_zone_requires_review(self) -> None:
        result = review_exit(
            ExitReviewInput(
                "SOXL",
                STRATEGY_A,
                "profit_protection",
                82,
                -3,
                60,
                True,
                unrealized_percent=24,
                drawdown_from_high_percent=-6,
                profit_protection_zone="giveback_review_zone",
            )
        )
        self.assertEqual(result.outcome, "review_required")

    def test_high_priority_quality_decline(self) -> None:
        result = review_exit(
            ExitReviewInput("BEX", STRATEGY_A, "paper_position", 80, -16, 60, True)
        )
        self.assertEqual(result.outcome, "high_priority_review")

    def test_warning_quality_decline(self) -> None:
        result = review_exit(
            ExitReviewInput("BEX", STRATEGY_A, "paper_position", 80, -9, 60, True)
        )
        self.assertEqual(result.outcome, "monitor_closely")

    def test_reentry_state_requires_review(self) -> None:
        result = review_exit(
            ExitReviewInput(
                "AMD",
                STRATEGY_A,
                "reentry_watch",
                80,
                0,
                60,
                True,
                reentry_state="reentry_ready",
            )
        )
        self.assertEqual(result.outcome, "review_required")

    def test_policy_requires_paper_mode(self) -> None:
        with self.assertRaises(ValueError):
            ExitReviewPolicy(paper_trade_mode=False)

    def test_multiple_reviews(self) -> None:
        results = review_exits(
            [
                ExitReviewInput("AMD", STRATEGY_A, "paper_position", 88, 0, 70, True),
                ExitReviewInput("SOXL", STRATEGY_B, "paper_position", 88, 0, 70, True, unrealized_percent=-11),
            ]
        )
        self.assertEqual(len(results), 2)

    def test_markdown_output(self) -> None:
        result = review_exit(ExitReviewInput("AMD", STRATEGY_A, "paper_position", 88, 0, 70, True))
        markdown = format_exit_review_markdown([result])
        self.assertIn("# Exit Review Report", markdown)
        self.assertIn("AMD", markdown)

    def test_file_outputs(self) -> None:
        result = review_exit(ExitReviewInput("AMD", STRATEGY_A, "paper_position", 88, 0, 70, True))
        output_dir = Path(self._testMethodName)
        try:
            json_path, md_path = write_exit_review_outputs(output_dir, [result])
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["paper_trade_mode"])
            self.assertEqual(payload["reviews"][0]["symbol"], "AMD")
        finally:
            for path in output_dir.glob("*"):
                path.unlink()
            output_dir.rmdir()


if __name__ == "__main__":
    unittest.main()

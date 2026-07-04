import json
import unittest
from pathlib import Path

from swing_trade_bot.trade_lifecycle_manager import (
    STRATEGY_A,
    STRATEGY_B,
    LifecycleInput,
    LifecyclePolicy,
    format_trade_lifecycle_markdown,
    review_lifecycle,
    review_lifecycles,
    write_trade_lifecycle_outputs,
)


class TradeLifecycleManagerTests(unittest.TestCase):
    def test_candidate_moves_to_entry_ready_when_evidence_is_strong(self) -> None:
        review = review_lifecycle(
            LifecycleInput(
                symbol="amd",
                active_strategy=STRATEGY_A,
                current_state="candidate",
                opportunity_quality_score=85,
                entry_score=80,
                market_regime_score=70,
                thesis_intact=True,
            )
        )

        self.assertEqual(review.symbol, "AMD")
        self.assertEqual(review.recommended_state, "entry_ready")
        self.assertEqual(review.suggested_action, "prepare_entry_review")

    def test_weak_candidate_remains_watchlist(self) -> None:
        review = review_lifecycle(
            LifecycleInput(
                symbol="BEX",
                active_strategy=STRATEGY_A,
                current_state="watchlist",
                opportunity_quality_score=60,
                entry_score=80,
                market_regime_score=70,
                thesis_intact=True,
            )
        )

        self.assertEqual(review.recommended_state, "watchlist")
        self.assertEqual(review.suggested_action, "monitor")

    def test_strategy_a_does_not_move_to_reentry_watch_on_drawdown_alone(self) -> None:
        review = review_lifecycle(
            LifecycleInput(
                symbol="AMDL",
                active_strategy=STRATEGY_A,
                current_state="paper_position",
                opportunity_quality_score=82,
                entry_score=55,
                market_regime_score=60,
                thesis_intact=True,
                entry_price=100,
                current_price=88,
                highest_price_since_entry=105,
            )
        )

        self.assertEqual(review.recommended_state, "paper_position")
        self.assertEqual(review.suggested_action, "continue_research_position")
        self.assertAlmostEqual(review.unrealized_percent or 0, -12.0)

    def test_strategy_b_moves_to_reentry_watch_on_configured_drawdown(self) -> None:
        review = review_lifecycle(
            LifecycleInput(
                symbol="AMDL",
                active_strategy=STRATEGY_B,
                current_state="paper_position",
                opportunity_quality_score=82,
                entry_score=55,
                market_regime_score=60,
                thesis_intact=True,
                entry_price=100,
                current_price=88,
                highest_price_since_entry=105,
            )
        )

        self.assertEqual(review.recommended_state, "reentry_watch")
        self.assertEqual(review.suggested_action, "research_reentry")

    def test_thesis_break_moves_to_review_required(self) -> None:
        review = review_lifecycle(
            LifecycleInput(
                symbol="AMD",
                active_strategy=STRATEGY_A,
                current_state="paper_position",
                opportunity_quality_score=90,
                entry_score=60,
                market_regime_score=60,
                thesis_intact=False,
                entry_price=100,
                current_price=95,
            )
        )

        self.assertEqual(review.recommended_state, "review_required")
        self.assertEqual(review.suggested_action, "review_thesis")

    def test_profit_zone_moves_to_profit_protection(self) -> None:
        review = review_lifecycle(
            LifecycleInput(
                symbol="SOXL",
                active_strategy=STRATEGY_A,
                current_state="paper_position",
                opportunity_quality_score=88,
                entry_score=75,
                market_regime_score=70,
                thesis_intact=True,
                entry_price=100,
                current_price=125,
                highest_price_since_entry=125,
            )
        )

        self.assertEqual(review.recommended_state, "profit_protection")
        self.assertEqual(review.suggested_action, "protect_paper_gain")
        self.assertAlmostEqual(review.unrealized_percent or 0, 25.0)

    def test_policy_requires_paper_mode(self) -> None:
        with self.assertRaises(ValueError):
            LifecyclePolicy(paper_trade_mode=False)

    def test_multiple_reviews_are_supported(self) -> None:
        reviews = review_lifecycles(
            [
                LifecycleInput("AMD", STRATEGY_A, "candidate", 80, 80, 70, True),
                LifecycleInput("BEX", STRATEGY_A, "watchlist", 50, 60, 70, True),
            ]
        )

        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].symbol, "AMD")

    def test_markdown_report_contains_rows(self) -> None:
        review = review_lifecycle(LifecycleInput("AMD", STRATEGY_A, "candidate", 80, 80, 70, True))
        markdown = format_trade_lifecycle_markdown([review])

        self.assertIn("# Trade Lifecycle Report", markdown)
        self.assertIn("| AMD |", markdown)

    def test_output_files_are_written(self) -> None:
        review = review_lifecycle(LifecycleInput("AMD", STRATEGY_A, "candidate", 80, 80, 70, True))
        output_dir = Path(self._testMethodName)
        try:
            json_path, md_path = write_trade_lifecycle_outputs(output_dir, [review])
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

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
        review = review_lifecycle(LifecycleInput("BEX", STRATEGY_A, "watchlist", 60, 80, 70, True))
        self.assertEqual(review.recommended_state, "watchlist")
        self.assertEqual(review.suggested_action, "monitor")

    def test_strategy_a_does_not_move_to_reentry_watch_on_drawdown_alone(self) -> None:
        review = review_lifecycle(
            LifecycleInput("AMDL", STRATEGY_A, "paper_position", 82, 55, 60, True, 100, 88, 105)
        )
        self.assertEqual(review.recommended_state, "paper_position")
        self.assertEqual(review.suggested_action, "continue_research_position")
        self.assertAlmostEqual(review.unrealized_percent or 0, -12.0)

    def test_strategy_b_moves_to_reentry_watch_on_configured_drawdown(self) -> None:
        review = review_lifecycle(
            LifecycleInput("AMDL", STRATEGY_B, "paper_position", 82, 55, 60, True, 100, 88, 105)
        )
        self.assertEqual(review.recommended_state, "reentry_watch")
        self.assertEqual(review.suggested_action, "research_reentry")

    def test_thesis_break_moves_to_review_required(self) -> None:
        review = review_lifecycle(
            LifecycleInput("AMD", STRATEGY_A, "paper_position", 90, 60, 60, False, 100, 95)
        )
        self.assertEqual(review.recommended_state, "review_required")
        self.assertEqual(review.suggested_action, "review_thesis")

    def test_profit_zone_moves_to_profit_protection(self) -> None:
        review = review_lifecycle(
            LifecycleInput("SOXL", STRATEGY_A, "paper_position", 88, 75, 70, True, 100, 125, 125)
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

    def test_output_files_publish_ai_cio_safe_contract(self) -> None:
        review = review_lifecycle(LifecycleInput("AMD", STRATEGY_A, "candidate", 80, 80, 70, True))
        output_dir = Path(self._testMethodName)
        try:
            json_path, md_path = write_trade_lifecycle_outputs(output_dir, [review])
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertFalse((output_dir / "trade_lifecycle_report.json.tmp").exists())
            self.assertFalse((output_dir / "trade_lifecycle_report.md.tmp").exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["strategy_id"], "SWING-001")
            self.assertTrue(payload["generated_at_utc"].endswith("Z"))
            self.assertTrue(payload["paper_trade_mode"])
            self.assertTrue(payload["advisory_only"])
            self.assertFalse(payload["live_trading_enabled"])
            self.assertFalse(payload["broker_execution_enabled"])
            self.assertFalse(payload["order_placement_enabled"])
            self.assertFalse(payload["capital_movement_enabled"])
            self.assertEqual(payload["review_count"], 1)
            self.assertEqual(payload["reviews"][0]["symbol"], "AMD")
        finally:
            if output_dir.exists():
                for path in output_dir.glob("*"):
                    path.unlink()
                output_dir.rmdir()


if __name__ == "__main__":
    unittest.main()

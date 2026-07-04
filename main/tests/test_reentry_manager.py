import json
import unittest
from pathlib import Path

from swing_trade_bot.reentry_manager import (
    STRATEGY_A,
    STRATEGY_B,
    ReentryInput,
    ReentryPolicy,
    format_reentry_markdown,
    review_reentries,
    review_reentry,
    write_reentry_outputs,
)


class ReentryManagerTests(unittest.TestCase):
    def test_context_required(self) -> None:
        review = review_reentry(ReentryInput("AMD", STRATEGY_A, "paper_position", 85, 80, 70, True))
        self.assertEqual(review.reentry_state, "no_reentry_context")

    def test_thesis_controls_blocked_state(self) -> None:
        review = review_reentry(ReentryInput("AMD", STRATEGY_A, "reentry_watch", 85, 80, 70, False, 1.5, 5))
        self.assertEqual(review.reentry_state, "reentry_blocked")

    def test_wait_period_is_respected(self) -> None:
        review = review_reentry(ReentryInput("SOXL", STRATEGY_B, "reentry_watch", 85, 80, 70, True, 1.5, 1))
        self.assertEqual(review.reentry_state, "reentry_watch")

    def test_low_quality_is_not_ready(self) -> None:
        review = review_reentry(ReentryInput("SOXL", STRATEGY_B, "reentry_watch", 60, 80, 70, True, 1.5, 5))
        self.assertEqual(review.reentry_state, "reentry_not_ready")

    def test_complete_evidence_becomes_ready(self) -> None:
        review = review_reentry(ReentryInput("AMDL", STRATEGY_B, "reentry_watch", 82, 78, 65, True, 2.0, 5))
        self.assertEqual(review.reentry_state, "reentry_ready")

    def test_partial_evidence_is_improving(self) -> None:
        review = review_reentry(ReentryInput("BEX", STRATEGY_A, "reentry_watch", 82, 65, 65, True, 2.0, 5))
        self.assertEqual(review.reentry_state, "reentry_setup_improving")

    def test_policy_requires_paper_mode(self) -> None:
        with self.assertRaises(ValueError):
            ReentryPolicy(paper_trade_mode=False)

    def test_multiple_reviews(self) -> None:
        reviews = review_reentries([
            ReentryInput("AMD", STRATEGY_A, "reentry_watch", 82, 78, 65, True, 2.0, 5),
            ReentryInput("BEX", STRATEGY_A, "paper_position", 82, 78, 65, True, 2.0, 5),
        ])
        self.assertEqual(len(reviews), 2)

    def test_markdown_output(self) -> None:
        review = review_reentry(ReentryInput("AMD", STRATEGY_A, "reentry_watch", 82, 78, 65, True, 2.0, 5))
        markdown = format_reentry_markdown([review])
        self.assertIn("# Reentry Report", markdown)
        self.assertIn("AMD", markdown)

    def test_file_outputs(self) -> None:
        review = review_reentry(ReentryInput("AMD", STRATEGY_A, "reentry_watch", 82, 78, 65, True, 2.0, 5))
        output_dir = Path(self._testMethodName)
        try:
            json_path, md_path = write_reentry_outputs(output_dir, [review])
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["paper_trade_mode"])
        finally:
            for path in output_dir.glob("*"):
                path.unlink()
            output_dir.rmdir()


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path

from swing_trade_bot.thesis_monitor import (
    STRATEGY_A,
    STRATEGY_B,
    ThesisEvidence,
    ThesisMonitorPolicy,
    format_thesis_monitor_markdown,
    review_theses,
    review_thesis,
    write_thesis_monitor_outputs,
)


class ThesisMonitorTests(unittest.TestCase):
    def test_strong_thesis(self) -> None:
        review = review_thesis(evidence("AMD", STRATEGY_A, 90))
        self.assertEqual(review.thesis_state, "strong")
        self.assertTrue(review.thesis_intact)

    def test_intact_thesis(self) -> None:
        review = review_thesis(evidence("AMD", STRATEGY_A, 75))
        self.assertEqual(review.thesis_state, "intact")
        self.assertTrue(review.thesis_intact)

    def test_weakening_thesis(self) -> None:
        review = review_thesis(evidence("BEX", STRATEGY_A, 62))
        self.assertEqual(review.thesis_state, "weakening")
        self.assertFalse(review.thesis_intact)

    def test_broken_thesis(self) -> None:
        review = review_thesis(evidence("BEX", STRATEGY_A, 45))
        self.assertEqual(review.thesis_state, "broken")
        self.assertFalse(review.thesis_intact)

    def test_material_quality_decline_can_weaken_thesis(self) -> None:
        item = evidence("AMD", STRATEGY_A, 82, trend=-13)
        review = review_thesis(item)
        self.assertEqual(review.thesis_state, "weakening")

    def test_insufficient_evidence_is_unknown(self) -> None:
        review = review_thesis(
            ThesisEvidence(
                symbol="AMD",
                active_strategy=STRATEGY_A,
                original_thesis="AI compute demand remains strong.",
                opportunity_quality_score=90,
                opportunity_quality_trend=0,
                fundamental_score=None,
                earnings_score=None,
                news_sentiment_score=None,
                conviction_score=None,
                sector_strength_score=None,
                market_regime_score=None,
                technical_health_score=None,
            )
        )
        self.assertEqual(review.thesis_state, "unknown")
        self.assertEqual(review.suggested_review_action, "insufficient_evidence")

    def test_strategy_b_is_supported(self) -> None:
        review = review_thesis(evidence("SOXL", STRATEGY_B, 88))
        self.assertEqual(review.active_strategy, STRATEGY_B)

    def test_policy_requires_paper_mode(self) -> None:
        with self.assertRaises(ValueError):
            ThesisMonitorPolicy(paper_trade_mode=False)

    def test_multiple_reviews(self) -> None:
        reviews = review_theses([evidence("AMD", STRATEGY_A, 90), evidence("BEX", STRATEGY_A, 45)])
        self.assertEqual(len(reviews), 2)

    def test_markdown_output(self) -> None:
        review = review_thesis(evidence("AMD", STRATEGY_A, 90))
        markdown = format_thesis_monitor_markdown([review])
        self.assertIn("# Thesis Monitor Report", markdown)
        self.assertIn("AMD", markdown)

    def test_file_outputs(self) -> None:
        review = review_thesis(evidence("AMD", STRATEGY_A, 90))
        output_dir = Path(self._testMethodName)
        try:
            json_path, md_path = write_thesis_monitor_outputs(output_dir, [review])
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["paper_trade_mode"])
            self.assertEqual(payload["version"], "1.4")
        finally:
            for path in output_dir.glob("*"):
                path.unlink()
            output_dir.rmdir()


def evidence(symbol: str, strategy: str, score: float, *, trend: float = 0.0) -> ThesisEvidence:
    return ThesisEvidence(
        symbol=symbol,
        active_strategy=strategy,
        original_thesis="Core research thesis remains under review.",
        opportunity_quality_score=score,
        opportunity_quality_trend=trend,
        fundamental_score=score,
        earnings_score=score,
        news_sentiment_score=score,
        conviction_score=score,
        sector_strength_score=score,
        market_regime_score=score,
        technical_health_score=score,
    )


if __name__ == "__main__":
    unittest.main()

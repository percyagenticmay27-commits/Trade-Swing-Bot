import json
import unittest
from pathlib import Path

from swing_trade_bot.profit_protection_manager import (
    STRATEGY_A,
    STRATEGY_B,
    ProfitProtectionInput,
    ProfitProtectionPolicy,
    format_profit_protection_markdown,
    review_profit_protection,
    review_profit_protections,
    write_profit_protection_outputs,
)


class ProfitProtectionManagerTests(unittest.TestCase):
    def test_missing_position_data_returns_missing_data_zone(self) -> None:
        review = review_profit_protection(
            ProfitProtectionInput("AMD", STRATEGY_A, None, 120, 130)
        )

        self.assertEqual(review.protection_zone, "no_position_data")
        self.assertEqual(review.suggested_review_action, "missing_data_review")

    def test_below_protection_zone(self) -> None:
        review = review_profit_protection(
            ProfitProtectionInput("AMD", STRATEGY_A, 100, 110, 112)
        )

        self.assertEqual(review.protection_zone, "below_protection_zone")
        self.assertEqual(review.suggested_review_action, "monitor")
        self.assertAlmostEqual(review.unrealized_percent or 0, 10.0)

    def test_standard_protection_zone_at_twenty_percent_gain(self) -> None:
        review = review_profit_protection(
            ProfitProtectionInput("AMD", STRATEGY_A, 100, 120, 121)
        )

        self.assertEqual(review.protection_zone, "standard_protection_zone")
        self.assertEqual(review.suggested_review_action, "standard_profit_review")

    def test_strong_trend_zone_at_thirty_percent_gain(self) -> None:
        review = review_profit_protection(
            ProfitProtectionInput("SOXL", STRATEGY_B, 100, 132, 134)
        )

        self.assertEqual(review.protection_zone, "strong_trend_zone")
        self.assertEqual(review.suggested_review_action, "strong_trend_review")

    def test_standard_giveback_review_zone(self) -> None:
        review = review_profit_protection(
            ProfitProtectionInput("AMD", STRATEGY_A, 100, 120, 127)
        )

        self.assertEqual(review.protection_zone, "giveback_review_zone")
        self.assertEqual(review.suggested_review_action, "giveback_review")
        self.assertLess(review.drawdown_from_high_percent or 0, -5.0)

    def test_strong_gain_giveback_review_zone(self) -> None:
        review = review_profit_protection(
            ProfitProtectionInput("SOXL", STRATEGY_B, 100, 132, 148)
        )

        self.assertEqual(review.protection_zone, "giveback_review_zone")
        self.assertEqual(review.suggested_review_action, "giveback_review")
        self.assertLess(review.drawdown_from_high_percent or 0, -10.0)

    def test_custom_policy_thresholds(self) -> None:
        review = review_profit_protection(
            ProfitProtectionInput("BEX", STRATEGY_A, 100, 115, 116),
            policy=ProfitProtectionPolicy(standard_gain_percent=15, strong_gain_percent=25),
        )

        self.assertEqual(review.protection_zone, "standard_protection_zone")

    def test_policy_requires_paper_mode(self) -> None:
        with self.assertRaises(ValueError):
            ProfitProtectionPolicy(paper_trade_mode=False)

    def test_multiple_reviews_are_supported(self) -> None:
        reviews = review_profit_protections(
            [
                ProfitProtectionInput("AMD", STRATEGY_A, 100, 110, 112),
                ProfitProtectionInput("SOXL", STRATEGY_B, 100, 132, 134),
            ]
        )

        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].symbol, "AMD")

    def test_markdown_report_contains_rows(self) -> None:
        review = review_profit_protection(ProfitProtectionInput("AMD", STRATEGY_A, 100, 120, 121))
        markdown = format_profit_protection_markdown([review])

        self.assertIn("# Profit Protection Report", markdown)
        self.assertIn("| AMD |", markdown)

    def test_output_files_are_written(self) -> None:
        review = review_profit_protection(ProfitProtectionInput("AMD", STRATEGY_A, 100, 120, 121))
        output_dir = Path(self._testMethodName)
        try:
            json_path, md_path = write_profit_protection_outputs(output_dir, [review])
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

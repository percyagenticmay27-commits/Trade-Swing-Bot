import unittest
import uuid
from pathlib import Path

from swing_trade_bot.confidence_engine import build_confidence_report


class ConfidenceEngineForwardMetricTests(unittest.TestCase):
    def test_blank_forward_metrics_remain_missing_and_unpromoted(self) -> None:
        root = Path.cwd() / f"confidence_forward_metric_test_{uuid.uuid4().hex}"
        root.mkdir()
        try:
            scores = root / "forward_metrics.csv"
            scores.write_text(
                "symbol,win_rate,profit_factor,number_of_trades\n"
                "NFLX,,,0\n",
                encoding="utf-8",
            )

            rows = build_confidence_report(scores, root, output_dir=root)
            nflx = {row.symbol: row for row in rows}["NFLX"]

            self.assertEqual(nflx.confidence, "LOW")
            self.assertIsNone(nflx.win_rate)
            self.assertIsNone(nflx.profit_factor)
            self.assertEqual(nflx.trade_count, 0)
            self.assertFalse(nflx.promotion_eligible)
            self.assertFalse(nflx.demotion_eligible)
        finally:
            for child in sorted(root.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                else:
                    child.rmdir()
            root.rmdir()

    def test_infinite_profit_factor_is_accepted_for_all_win_forward_evidence(self) -> None:
        root = Path.cwd() / f"confidence_forward_metric_test_{uuid.uuid4().hex}"
        root.mkdir()
        try:
            scores = root / "forward_metrics.csv"
            scores.write_text(
                "symbol,win_rate,profit_factor,number_of_trades\n"
                "NFLX,100.0,inf,15\n",
                encoding="utf-8",
            )

            rows = build_confidence_report(scores, root, output_dir=root)
            nflx = {row.symbol: row for row in rows}["NFLX"]

            self.assertTrue(nflx.promotion_eligible)
        finally:
            for child in sorted(root.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                else:
                    child.rmdir()
            root.rmdir()


if __name__ == "__main__":
    unittest.main()

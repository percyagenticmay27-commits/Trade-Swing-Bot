import unittest

from swing_trade_bot.indicators import ema, rsi, sma, volume_average


class IndicatorTests(unittest.TestCase):
    def test_sma_and_volume_average(self) -> None:
        self.assertEqual(sma([1, 2, 3, 4], 3), 3)
        self.assertEqual(volume_average([100, 200, 300], 2), 250)

    def test_ema_uses_sma_seed(self) -> None:
        self.assertAlmostEqual(ema([1, 2, 3, 4], 3), 3.0)

    def test_rsi_edge_cases(self) -> None:
        self.assertEqual(rsi([1, 2, 3, 4], 3), 100.0)
        self.assertEqual(rsi([2, 2, 2, 2], 3), 50.0)

    def test_wilder_rsi_14_known_fixture(self) -> None:
        closes = [
            44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
            45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
        ]
        self.assertAlmostEqual(rsi(closes, 14), 70.464135, places=6)

    def test_insufficient_data_returns_none(self) -> None:
        self.assertIsNone(sma([1, 2], 3))
        self.assertIsNone(ema([1, 2], 3))
        self.assertIsNone(rsi([1, 2, 3], 3))


if __name__ == "__main__":
    unittest.main()

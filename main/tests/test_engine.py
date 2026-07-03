import unittest
from datetime import date, timedelta
from unittest.mock import patch

from swing_trade_bot import MarketBar, StrategyConfig, SwingTradeEngine


def bars(close: float = 100.0, volume: float = 200.0) -> list[MarketBar]:
    start = date(2026, 1, 1)
    return [
        MarketBar(start + timedelta(days=index), close, 100.0 if index < 50 else volume)
        for index in range(51)
    ]


def bars_ending(end: date, close: float = 100.0, volume: float = 200.0) -> list[MarketBar]:
    start = end - timedelta(days=50)
    return [
        MarketBar(start + timedelta(days=index), close, 100.0 if index < 50 else volume)
        for index in range(51)
    ]


def rising_benchmark() -> list[MarketBar]:
    result = bars(close=90.0)
    result[-1] = MarketBar(result[-1].date, 100.0, result[-1].volume)
    return result


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SwingTradeEngine(
            StrategyConfig(symbols=("SOXL",)), account_value=100_000.0
        )
        self.benchmarks = {"SPY": rising_benchmark(), "QQQ": rising_benchmark()}

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_entry_opens_sized_paper_position(self, *_: object) -> None:
        signal = self.engine.evaluate("soxl", bars(), self.benchmarks)

        self.assertEqual(signal.signal, "BUY")
        self.assertEqual(signal.entry_price, 100.0)
        self.assertEqual(signal.stop_price, 90.0)
        self.assertEqual(signal.suggested_position_size, 10_000.0)
        self.assertTrue(self.engine.positions["SOXL"].is_open)

    def test_15_percent_profit_moves_stop_to_breakeven(self) -> None:
        state = self.engine.positions["SOXL"]
        self.engine._open_position(state, 100.0)
        signal = self.engine._manage_open_position(state, 115.0)
        self.assertEqual(signal.stop_price, 100.0)

    def test_20_percent_profit_activates_five_percent_trail(self) -> None:
        state = self.engine.positions["SOXL"]
        self.engine._open_position(state, 100.0)
        signal = self.engine._manage_open_position(state, 120.0)
        self.assertEqual(signal.stop_price, 114.0)

    def test_30_percent_profit_changes_trail_to_ten_percent(self) -> None:
        state = self.engine.positions["SOXL"]
        self.engine._open_position(state, 100.0)
        signal = self.engine._manage_open_position(state, 130.0)
        self.assertEqual(signal.stop_price, 117.0)

    def test_switch_to_ten_percent_trail_never_lowers_stop(self) -> None:
        state = self.engine.positions["SOXL"]
        self.engine._open_position(state, 100.0)

        five_percent_trail = self.engine._manage_open_position(state, 129.0)
        self.assertEqual(five_percent_trail.stop_price, 122.55)

        ten_percent_trail = self.engine._manage_open_position(state, 130.0)
        self.assertEqual(ten_percent_trail.stop_price, 122.55)
        self.assertGreaterEqual(ten_percent_trail.stop_price, five_percent_trail.stop_price)

    def test_close_below_stop_generates_sell(self) -> None:
        state = self.engine.positions["SOXL"]
        self.engine._open_position(state, 100.0)
        self.engine._manage_open_position(state, 130.0)
        signal = self.engine._manage_open_position(state, 116.0)

        self.assertEqual(signal.signal, "SELL")
        self.assertFalse(state.is_open)
        self.assertTrue(state.awaiting_reentry)

    @patch("swing_trade_bot.engine.rsi", return_value=60.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=99.0)
    def test_wait_for_reentry_after_sell(self, *_: object) -> None:
        state = self.engine.positions["SOXL"]
        self.engine._open_position(state, 100.0)
        self.engine._manage_open_position(state, 130.0)
        self.engine._manage_open_position(state, 116.0)

        signal = self.engine.evaluate("SOXL", bars(), self.benchmarks)
        self.assertEqual(signal.signal, "WAIT_FOR_REENTRY")

    @patch("swing_trade_bot.engine.rsi", return_value=50.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=99.0)
    def test_reentry_buy_after_pullback_and_market_filters(self, *_: object) -> None:
        self.engine.positions["SOXL"].awaiting_reentry = True
        signal = self.engine.evaluate("SOXL", bars(), self.benchmarks)

        self.assertEqual(signal.signal, "BUY")
        self.assertIn("RE-ENTRY BUY", signal.reason)

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_soxl_buy_is_blocked_when_qqq_filter_fails(self, *_: object) -> None:
        benchmarks = {"SPY": rising_benchmark(), "QQQ": bars(close=90.0)}
        signal = self.engine.evaluate("SOXL", bars(), benchmarks)
        self.assertEqual(signal.signal, "HOLD")
        self.assertIn("QQQ is above", signal.reason)

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_all_buys_are_blocked_when_spy_filter_fails(self, *_: object) -> None:
        benchmarks = {"SPY": bars(close=90.0), "QQQ": rising_benchmark()}
        signal = self.engine.evaluate("SOXL", bars(), benchmarks)
        self.assertEqual(signal.signal, "HOLD")
        self.assertIn("SPY is above", signal.reason)

    def test_position_size_is_capped_at_twenty_percent(self) -> None:
        engine = SwingTradeEngine(
            StrategyConfig(symbols=("BEX",), initial_stop_percent=0.02),
            account_value=100_000.0,
        )
        self.assertEqual(engine.calculate_position_size(), 20_000.0)

    def test_live_mode_and_order_placement_are_blocked(self) -> None:
        with self.assertRaises(ValueError):
            SwingTradeEngine(paper_trade_mode=False)
        with self.assertRaises(RuntimeError):
            self.engine.place_order("SOXL", "buy", 1)

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_nbis_earnings_blackout_blocks_nebx_entries(self, *_: object) -> None:
        engine = SwingTradeEngine(StrategyConfig(symbols=("NEBX",)))
        current_bars = bars_ending(date(2026, 2, 20))

        signal = engine.evaluate(
            "NEBX",
            current_bars,
            {"SPY": rising_benchmark()},
            {"NBIS": date(2026, 2, 27)},
        )

        self.assertEqual(signal.signal, "HOLD")
        self.assertIn("NEBX is earnings sensitive through NBIS", signal.reason)
        self.assertIn("entry blackout", signal.reason)

    def test_one_trading_day_before_nbis_earnings_forces_nbis_and_nebx_sell(self) -> None:
        engine = SwingTradeEngine(StrategyConfig(symbols=("NBIS", "NEBX")))
        current_bars = bars_ending(date(2026, 2, 20))
        for symbol in ("NBIS", "NEBX"):
            engine._open_position(engine.positions[symbol], 100.0)

        nbis_signal = engine.evaluate(
            "NBIS",
            current_bars,
            {"SPY": rising_benchmark()},
            {"NBIS": date(2026, 2, 23)},
        )
        nebx_signal = engine.evaluate(
            "NEBX",
            current_bars,
            {"SPY": rising_benchmark()},
            {"NBIS": date(2026, 2, 23)},
        )

        self.assertEqual(nbis_signal.signal, "SELL")
        self.assertEqual(nebx_signal.signal, "SELL")
        self.assertIn("move proceeds to SGOV", nbis_signal.reason)
        self.assertIn("move proceeds to SGOV", nebx_signal.reason)
        self.assertFalse(engine.positions["NBIS"].is_open)
        self.assertFalse(engine.positions["NEBX"].is_open)
        self.assertTrue(engine.positions["NBIS"].awaiting_reentry)
        self.assertTrue(engine.positions["NEBX"].awaiting_reentry)

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_post_earnings_wait_blocks_then_allows_independent_reentry(self, *_: object) -> None:
        engine = SwingTradeEngine(StrategyConfig(symbols=("NBIS", "NEBX")))
        earnings = {"NBIS": date(2026, 2, 23)}

        waiting_signal = engine.evaluate(
            "NEBX",
            bars_ending(date(2026, 2, 25)),
            {"SPY": rising_benchmark()},
            earnings,
        )
        self.assertEqual(waiting_signal.signal, "HOLD")
        self.assertIn("post-earnings wait", waiting_signal.reason)

        nbis_signal = engine.evaluate(
            "NBIS",
            bars_ending(date(2026, 2, 26)),
            {"SPY": rising_benchmark()},
            earnings,
        )
        nebx_signal = engine.evaluate(
            "NEBX",
            bars_ending(date(2026, 2, 26)),
            {"SPY": rising_benchmark()},
            earnings,
        )

        self.assertEqual(nbis_signal.signal, "BUY")
        self.assertEqual(nebx_signal.signal, "BUY")


if __name__ == "__main__":
    unittest.main()

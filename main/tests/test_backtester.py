import json
import unittest
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from swing_trade_bot.backtester import SwingTradeBacktester, format_table, results_to_json
from swing_trade_bot.config import StrategyConfig
from swing_trade_bot.engine import SwingTradeEngine
from swing_trade_bot.paper_runner import load_csv
from swing_trade_bot.position_state import MarketBar, SignalResult


def base_bars() -> list[MarketBar]:
    start = date(2026, 1, 1)
    return [
        MarketBar(
            date=start + timedelta(days=index),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=200.0 if index == 50 else 100.0,
        )
        for index in range(51)
    ]


def stop_scenario_bars() -> list[MarketBar]:
    result = base_bars()
    start = result[0].date
    result.extend(
        [
            MarketBar(start + timedelta(days=51), 120.0, 100.0, 100.0, 121.0, 100.0),
            MarketBar(start + timedelta(days=52), 118.0, 100.0, 118.0, 119.0, 110.0),
        ]
    )
    return result


def next_open_bars() -> list[MarketBar]:
    result = base_bars()
    start = result[0].date
    result.extend(
        [
            MarketBar(start + timedelta(days=51), 110.0, 100.0, 110.0, 111.0, 109.0),
            MarketBar(start + timedelta(days=52), 111.0, 100.0, 111.0, 112.0, 110.0),
        ]
    )
    return result


def losing_bars() -> list[MarketBar]:
    result = base_bars()
    start = result[0].date
    result.append(MarketBar(start + timedelta(days=51), 89.0, 100.0, 100.0, 101.0, 89.0))
    return result


def normal_sell_bars() -> list[MarketBar]:
    result = base_bars()
    start = result[0].date
    result.extend(
        [
            MarketBar(start + timedelta(days=51), 105.0, 100.0, 100.0, 106.0, 95.0),
            MarketBar(start + timedelta(days=52), 102.0, 100.0, 104.0, 105.0, 100.0),
        ]
    )
    return result


def benchmark_bars(length: int = 53) -> list[MarketBar]:
    start = date(2026, 1, 1)
    return [
        MarketBar(start + timedelta(days=index), 90.0 if index < 50 else 100.0, 100.0)
        for index in range(length)
    ]


class BacktesterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backtester = SwingTradeBacktester(
            StrategyConfig(symbols=("SOXL",)), account_value=100_000.0
        )
        self.market_data = {
            "SOXL": stop_scenario_bars(),
            "SPY": benchmark_bars(),
            "QQQ": benchmark_bars(),
        }

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_day_by_day_metrics_and_buy_hold_comparison(self, *_: object) -> None:
        result = self.backtester.run(self.market_data)[0]

        self.assertAlmostEqual(result.total_return, 1.4)
        self.assertAlmostEqual(result.buy_and_hold_return, 18.0)
        self.assertEqual(result.number_of_trades, 1)
        self.assertEqual(result.win_rate, 100.0)
        self.assertAlmostEqual(result.average_win, 14.0)
        self.assertIsNone(result.average_loss)
        self.assertAlmostEqual(result.max_drawdown, 0.5882352941)
        self.assertAlmostEqual(result.best_trade, 14.0)
        self.assertAlmostEqual(result.worst_trade, 14.0)
        self.assertEqual(result.average_holding_period, 1.0)
        self.assertEqual(result.ending_account_value, 101_400.0)

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_buy_signal_enters_at_next_day_open(self, *_: object) -> None:
        market_data = {
            "SOXL": next_open_bars(),
            "SPY": benchmark_bars(),
            "QQQ": benchmark_bars(),
        }
        trade = self.backtester.run(market_data)[0].trades[0]

        self.assertEqual(trade.entry_date, date(2026, 2, 21))
        self.assertEqual(trade.entry_price, 110.0)

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_intraday_low_exits_at_stop_price(self, *_: object) -> None:
        trade = self.backtester.run(self.market_data)[0].trades[0]

        self.assertEqual(trade.exit_price, 114.0)
        self.assertIn("Intraday low", trade.exit_reason)
        self.assertEqual(stop_scenario_bars()[-1].close, 118.0)

    def test_normal_sell_sets_reentry_state(self) -> None:
        market_data = {
            "SOXL": normal_sell_bars(),
            "SPY": benchmark_bars(),
            "QQQ": benchmark_bars(),
        }
        calls = 0
        sell_seen = False
        reentry_state_seen = False

        def evaluate_at_close(
            engine: SwingTradeEngine,
            symbol: str,
            bars: list[MarketBar],
            benchmark_data: object,
        ) -> SignalResult:
            nonlocal calls, sell_seen, reentry_state_seen
            calls += 1
            state = engine.positions[symbol]
            if calls == 1:
                return SignalResult(
                    symbol, "BUY", "entry", None, bars[-1].close,
                    None, None, None, 10_000.0,
                )
            if calls == 2:
                sell_seen = True
                return SignalResult(
                    symbol, "SELL", "normal close sell", state.entry_price,
                    bars[-1].close, state.highest_close, state.current_stop,
                    5.0, state.position_size,
                )

            reentry_state_seen = (
                not state.is_open
                and state.awaiting_reentry
                and state.entry_price is None
                and state.highest_close is None
                and state.current_stop is None
            )
            return SignalResult(
                symbol, "WAIT_FOR_REENTRY", "re-entry check reached", None,
                bars[-1].close, None, None, None, None,
            )

        with patch.object(
            SwingTradeEngine,
            "evaluate",
            autospec=True,
            side_effect=evaluate_at_close,
        ):
            result = self.backtester.run(market_data)[0]

        self.assertEqual(result.number_of_trades, 1)
        self.assertTrue(sell_seen)
        self.assertEqual(result.trades[0].exit_reason, "normal close sell")
        self.assertTrue(reentry_state_seen)

    @patch("swing_trade_bot.engine.rsi", return_value=70.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_no_trade_metrics(self, *_: object) -> None:
        result = self.backtester.run(self.market_data)[0]
        self.assertEqual(result.total_return, 0.0)
        self.assertEqual(result.number_of_trades, 0)
        self.assertEqual(result.win_rate, 0.0)
        self.assertIsNone(result.best_trade)

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_loss_metrics_and_drawdown(self, *_: object) -> None:
        market_data = {
            "SOXL": losing_bars(),
            "SPY": benchmark_bars(52),
            "QQQ": benchmark_bars(52),
        }
        result = self.backtester.run(market_data)[0]

        self.assertAlmostEqual(result.total_return, -1.0)
        self.assertIsNone(result.average_win)
        self.assertAlmostEqual(result.average_loss, -10.0)
        self.assertAlmostEqual(result.max_drawdown, 1.0)
        self.assertAlmostEqual(result.worst_trade, -10.0)

    @patch("swing_trade_bot.engine.rsi", return_value=55.0)
    @patch("swing_trade_bot.engine.sma", return_value=90.0)
    @patch("swing_trade_bot.engine.ema", return_value=95.0)
    def test_json_and_readable_table_outputs(self, *_: object) -> None:
        results = self.backtester.run(self.market_data)
        payload = json.loads(results_to_json(results))
        table = format_table(results)

        self.assertTrue(payload["paper_trade_mode"])
        self.assertEqual(payload["results"][0]["trades"][0]["entry_date"], "2026-02-21")
        self.assertIn("Buy/Hold", table)
        self.assertIn("SOXL", table)

    def test_close_only_csv_remains_supported(self) -> None:
        csv_text = "date,close,volume\n2026-01-02,100.25,1234567\n"
        with patch.object(Path, "open", return_value=StringIO(csv_text)):
            bar = load_csv(Path("legacy.csv"))[0]

        self.assertEqual(bar.open_price, 100.25)
        self.assertEqual(bar.high_price, 100.25)
        self.assertEqual(bar.low_price, 100.25)

    def test_ohlcv_csv_loads_all_prices(self) -> None:
        csv_text = (
            "date,open,high,low,close,volume\n"
            "2026-01-02,99.5,101.0,99.25,100.25,1234567\n"
        )
        with patch.object(Path, "open", return_value=StringIO(csv_text)):
            bar = load_csv(Path("ohlcv.csv"))[0]

        self.assertEqual(bar.open_price, 99.5)
        self.assertEqual(bar.high_price, 101.0)
        self.assertEqual(bar.low_price, 99.25)
        self.assertEqual(bar.close, 100.25)

    def test_live_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SwingTradeBacktester(paper_trade_mode=False)


if __name__ == "__main__":
    unittest.main()

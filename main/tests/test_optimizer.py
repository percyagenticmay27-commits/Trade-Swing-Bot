import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from swing_trade_bot.backtester import BacktestResult
from swing_trade_bot.config import StrategyConfig
from swing_trade_bot.optimizer import OptimizationGrid, StrategyOptimizer, write_outputs
from swing_trade_bot.position_state import MarketBar


def market_bars() -> list[MarketBar]:
    start = date(2025, 1, 1)
    return [
        MarketBar(start + timedelta(days=index), 100.0, 100.0)
        for index in range(60)
    ]


class OptimizerTests(unittest.TestCase):
    def test_default_grid_contains_2916_combinations(self) -> None:
        self.assertEqual(len(tuple(OptimizationGrid().parameter_sets())), 2916)

    def test_optimizer_ranks_each_symbol_independently(self) -> None:
        grid = OptimizationGrid(
            initial_stops=(0.08, 0.10),
            break_even_triggers=(0.15,),
            trailing_one_triggers=(0.20,),
            trailing_one_distances=(0.05,),
            trailing_two_triggers=(0.30,),
            trailing_two_distances=(0.10,),
            rsi_entry_ranges=((45.0, 65.0),),
        )
        optimizer = StrategyOptimizer(
            StrategyConfig(symbols=("SOXL",)),
            grid=grid,
            account_value=100_000.0,
        )

        def fake_run(backtester: object, market_data: object) -> list[BacktestResult]:
            stop = backtester.config.initial_stop_percent
            total_return = 10.0 if stop == 0.10 else 5.0
            ending_value = 100_000.0 * (1.0 + total_return / 100.0)
            return [
                BacktestResult(
                    symbol="SOXL",
                    total_return=total_return,
                    buy_and_hold_return=2.0,
                    number_of_trades=0,
                    win_rate=0.0,
                    average_win=None,
                    average_loss=None,
                    max_drawdown=1.0,
                    best_trade=None,
                    worst_trade=None,
                    average_holding_period=None,
                    starting_account_value=100_000.0,
                    ending_account_value=ending_value,
                    trades=(),
                    equity_curve=(100_000.0, ending_value),
                )
            ]

        data = {"SOXL": market_bars(), "SPY": market_bars(), "QQQ": market_bars()}
        with patch(
            "swing_trade_bot.optimizer.SwingTradeBacktester.run",
            autospec=True,
            side_effect=fake_run,
        ):
            best, ranked = optimizer.optimize(data)

        self.assertEqual(len(ranked), 2)
        self.assertEqual(best[0].rank, 1)
        self.assertEqual(best[0].total_return, 10.0)
        self.assertAlmostEqual(best[0].score, 0.35)
        self.assertEqual(best[0].normalized_return, 1.0)
        self.assertIn("score", best[0].best_row())
        self.assertEqual(best[0].parameters.initial_stop, 0.10)
        self.assertIn("parameter_set", best[0].json_result())

    def test_write_outputs_creates_required_artifact_names(self) -> None:
        optimizer = StrategyOptimizer(
            StrategyConfig(symbols=("SOXL",)),
            grid=OptimizationGrid(
                initial_stops=(0.10,),
                break_even_triggers=(0.15,),
                trailing_one_triggers=(0.20,),
                trailing_one_distances=(0.05,),
                trailing_two_triggers=(0.30,),
                trailing_two_distances=(0.10,),
                rsi_entry_ranges=((45.0, 65.0),),
            ),
        )
        data = {"SOXL": market_bars(), "SPY": market_bars(), "QQQ": market_bars()}

        def fake_run(backtester: object, market_data: object) -> list[BacktestResult]:
            return [
                BacktestResult(
                    symbol="SOXL",
                    total_return=1.0,
                    buy_and_hold_return=0.0,
                    number_of_trades=0,
                    win_rate=0.0,
                    average_win=None,
                    average_loss=None,
                    max_drawdown=0.0,
                    best_trade=None,
                    worst_trade=None,
                    average_holding_period=None,
                    starting_account_value=100_000.0,
                    ending_account_value=101_000.0,
                    trades=(),
                    equity_curve=(100_000.0, 101_000.0),
                )
            ]

        with patch("swing_trade_bot.optimizer.SwingTradeBacktester.run", autospec=True, side_effect=fake_run):
            best, ranked = optimizer.optimize(data)
        with patch("swing_trade_bot.optimizer._write_csv") as write_csv, patch.object(
            Path, "mkdir"
        ), patch.object(Path, "write_text") as write_text:
            paths = write_outputs(Path("out"), best, ranked)

        self.assertEqual(
            [path.name for path in paths],
            [
                "results.csv",
                "results.json",
                "ranked_results.csv",
                "best_by_return.csv",
                "best_by_sharpe.csv",
                "best_by_drawdown.csv",
                "best_by_score.csv",
            ],
        )
        self.assertEqual(write_csv.call_count, 6)
        write_text.assert_called_once()

    def test_live_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            StrategyOptimizer(paper_trade_mode=False)


if __name__ == "__main__":
    unittest.main()

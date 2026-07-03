import csv
import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from swing_trade_bot.position_state import MarketBar
from swing_trade_bot.strategy_lab import (
    STRATEGY_A,
    STRATEGY_B,
    StrategyLab,
    StrategyLabResult,
    format_recommendations,
    format_strategy_report,
    write_strategy_lab_outputs,
)


class StrategyLabTests(unittest.TestCase):
    def test_runs_strategy_a_and_b_for_each_symbol(self) -> None:
        with entry_indicators():
            results = StrategyLab(symbols=("SOXL",), account_value=100_000.0).run({"SOXL": lab_bars()})

        self.assertEqual([result.strategy for result in results], [STRATEGY_A, STRATEGY_B])
        self.assertTrue(all(result.symbol == "SOXL" for result in results))

    def test_strategy_b_partial_exits_can_outperform_strategy_a(self) -> None:
        with entry_indicators():
            results = StrategyLab(symbols=("SOXL",), account_value=100_000.0).run({"SOXL": lab_bars()})

        by_strategy = {result.strategy: result for result in results}
        self.assertGreater(by_strategy[STRATEGY_B].total_return, by_strategy[STRATEGY_A].total_return)
        self.assertEqual(by_strategy[STRATEGY_A].trade_count, 1)
        self.assertEqual(by_strategy[STRATEGY_B].trade_count, 1)

    def test_strategy_b_switch_requires_three_months_twenty_trades_profit_factor_and_drawdown(self) -> None:
        lab = StrategyLab(symbols=("SOXL",))
        strategy_a = metric_result("SOXL", STRATEGY_A, total_return=10, profit_factor=1.5, drawdown=8, trades=25)
        strategy_b = metric_result("SOXL", STRATEGY_B, total_return=20, profit_factor=1.6, drawdown=12, trades=20)

        not_yet = lab.recommend([strategy_a, strategy_b], review_history={"SOXL": 1})[0]
        eligible = lab.recommend([strategy_a, strategy_b], review_history={"SOXL": 2})[0]
        bad_drawdown = lab.recommend(
            [strategy_a, metric_result("SOXL", STRATEGY_B, total_return=20, profit_factor=1.6, drawdown=20, trades=20)],
            review_history={"SOXL": 2},
        )[0]

        self.assertFalse(not_yet.switch_eligible)
        self.assertTrue(eligible.switch_eligible)
        self.assertEqual(eligible.recommended_strategy, STRATEGY_B)
        self.assertFalse(bad_drawdown.switch_eligible)

    def test_different_symbols_can_receive_different_recommendations(self) -> None:
        lab = StrategyLab(symbols=("SOXL", "NEBX"))
        results = [
            metric_result("SOXL", STRATEGY_A, total_return=15, profit_factor=2, drawdown=5, trades=30),
            metric_result("SOXL", STRATEGY_B, total_return=10, profit_factor=2, drawdown=5, trades=30),
            metric_result("NEBX", STRATEGY_A, total_return=5, profit_factor=1.2, drawdown=10, trades=25),
            metric_result("NEBX", STRATEGY_B, total_return=20, profit_factor=1.5, drawdown=12, trades=20),
        ]

        rows = lab.recommend(results, review_history={"SOXL": 2, "NEBX": 2})
        by_symbol = {row.symbol: row for row in rows}

        self.assertEqual(by_symbol["SOXL"].recommended_strategy, STRATEGY_A)
        self.assertEqual(by_symbol["NEBX"].recommended_strategy, STRATEGY_B)

    def test_writes_comparison_json_and_recommendation_csv(self) -> None:
        with workspace_temp_dir() as directory:
            results = [
                metric_result("SOXL", STRATEGY_A, total_return=10, profit_factor=2, drawdown=4, trades=25),
                metric_result("SOXL", STRATEGY_B, total_return=15, profit_factor=2.5, drawdown=5, trades=20),
            ]
            recommendations = StrategyLab(symbols=("SOXL",)).recommend(results, review_history={"SOXL": 2})
            comparison_csv, comparison_json, recommendations_csv = write_strategy_lab_outputs(
                directory,
                results,
                recommendations,
            )
            with comparison_csv.open(newline="", encoding="utf-8") as input_file:
                comparison_rows = list(csv.DictReader(input_file))
            payload = json.loads(comparison_json.read_text(encoding="utf-8"))
            with recommendations_csv.open(newline="", encoding="utf-8") as input_file:
                recommendation_rows = list(csv.DictReader(input_file))

        self.assertEqual(comparison_rows[0]["symbol"], "SOXL")
        self.assertTrue(payload["paper_trade_mode"])
        self.assertEqual(recommendation_rows[0]["recommended_strategy"], STRATEGY_B)

    def test_report_formatters_include_strategy_and_recommendation_fields(self) -> None:
        result = metric_result("SOXL", STRATEGY_A, total_return=10, profit_factor=2, drawdown=4, trades=25)
        recommendation = StrategyLab(symbols=("SOXL",)).recommend(
            [
                result,
                metric_result("SOXL", STRATEGY_B, total_return=5, profit_factor=1, drawdown=4, trades=25),
            ]
        )[0]

        self.assertIn("Strategy", format_strategy_report([result]))
        self.assertIn("Recommended", format_recommendations([recommendation]))

    def test_live_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            StrategyLab(paper_trade_mode=False)


def lab_bars() -> list[MarketBar]:
    start = date(2025, 1, 1)
    bars = [
        MarketBar(start + timedelta(days=index), open=100.0, high=101.0, low=99.0, close=100.0, volume=200.0)
        for index in range(50)
    ]
    prices = [
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 121.0, 99.0, 120.0),
        (120.0, 136.0, 119.0, 135.0),
        (135.0, 136.0, 120.0, 125.0),
        (135.0, 176.0, 134.0, 175.0),
        (175.0, 176.0, 157.0, 160.0),
        (160.0, 160.0, 150.0, 151.0),
    ]
    for offset, (open_price, high, low, close) in enumerate(prices, 50):
        bars.append(
            MarketBar(
                start + timedelta(days=offset),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=200.0 if offset < 54 else 50.0,
            )
        )
    return bars


def metric_result(
    symbol: str,
    strategy: str,
    *,
    total_return: float,
    profit_factor: float,
    drawdown: float,
    trades: int,
) -> StrategyLabResult:
    return StrategyLabResult(
        symbol=symbol,
        strategy=strategy,  # type: ignore[arg-type]
        total_return=total_return,
        cagr=total_return,
        win_rate=60.0,
        profit_factor=profit_factor,
        max_drawdown=drawdown,
        sharpe_ratio=1.0,
        trade_count=trades,
        average_gain=10.0,
        average_loss=-5.0,
        starting_account_value=100_000.0,
        ending_account_value=100_000.0 * (1 + total_return / 100),
        trades=(),
        equity_curve=(100_000.0, 100_000.0 * (1 + total_return / 100)),
    )


def entry_indicators():
    class IndicatorPatch:
        def __enter__(self) -> None:
            self.patchers = [
                patch("swing_trade_bot.strategy_lab.ema", return_value=90.0),
                patch("swing_trade_bot.strategy_lab.sma", return_value=90.0),
                patch("swing_trade_bot.strategy_lab.rsi", return_value=55.0),
                patch("swing_trade_bot.strategy_lab.volume_average", return_value=100.0),
            ]
            for patcher in self.patchers:
                patcher.start()

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for patcher in self.patchers:
                patcher.stop()

    return IndicatorPatch()


def workspace_temp_dir():
    class WorkspaceTempDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"strategy_lab_test_{date.today().isoformat()}_{id(self)}"

        def __enter__(self) -> Path:
            self.path.mkdir()
            return self.path

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for child in self.path.iterdir():
                child.unlink()
            self.path.rmdir()

    return WorkspaceTempDir()


if __name__ == "__main__":
    unittest.main()

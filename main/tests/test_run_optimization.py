import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from swing_trade_bot.data_tools import SymbolValidation
from swing_trade_bot.optimizer import ParameterSet
from swing_trade_bot.run_optimization import (
    format_optimization_summary,
    run_optimization,
    run_optimization_report,
)


class RunOptimizationTests(unittest.TestCase):
    def test_refuses_to_run_when_validation_fails(self) -> None:
        invalid = [
            SymbolValidation(
                symbol="SOXL",
                path=Path("data/SOXL.csv"),
                exists=True,
                invalid_rows=("row 2: missing close",),
            )
        ]
        with patch("swing_trade_bot.run_optimization.validate_data_directory", return_value=invalid):
            with self.assertRaises(ValueError) as raised:
                run_optimization(Path("data"), Path("results"), account_value=100_000.0)

        self.assertIn("Data validation failed", str(raised.exception))

    def test_strict_mode_fails_when_any_trade_symbol_is_invalid(self) -> None:
        validations = partial_validations()
        with patch("swing_trade_bot.run_optimization.validate_data_directory", return_value=validations):
            with self.assertRaises(ValueError) as raised:
                run_optimization(Path("data"), Path("results"), account_value=100_000.0)

        self.assertIn("Data validation failed", str(raised.exception))

    def test_runs_optimizer_and_writes_expected_outputs_after_validation(self) -> None:
        valid = [
            SymbolValidation(
                symbol="SOXL",
                path=Path("data/SOXL.csv"),
                exists=True,
                row_count=252,
                start_date=date(2025, 1, 1),
                end_date=date(2025, 9, 9),
            )
        ]
        best = [optimization_result("SOXL")]
        ranked = [optimization_result("SOXL")]
        with patch("swing_trade_bot.run_optimization.validate_data_directory", return_value=valid), patch(
            "swing_trade_bot.run_optimization.load_market_data", return_value={}
        ), patch("swing_trade_bot.run_optimization.StrategyOptimizer") as optimizer_class, patch(
            "swing_trade_bot.run_optimization.write_outputs"
        ) as write_outputs:
            optimizer_class.return_value.optimize.return_value = (best, ranked)

            actual_best, actual_ranked = run_optimization(
                Path("data"),
                Path("results"),
                account_value=100_000.0,
            )

        self.assertEqual(actual_best, best)
        self.assertEqual(actual_ranked, ranked)
        optimizer_class.assert_called_once()
        self.assertEqual(optimizer_class.call_args.kwargs["account_value"], 100_000.0)
        self.assertTrue(optimizer_class.call_args.kwargs["paper_trade_mode"])
        optimizer_class.return_value.optimize.assert_called_once_with({})
        write_outputs.assert_called_once_with(Path("results"), best, ranked)

    def test_allow_partial_skips_invalid_trade_symbols(self) -> None:
        best = [optimization_result("SOXL"), optimization_result("TQQQ"), optimization_result("IONL")]
        ranked = best
        with patch(
            "swing_trade_bot.run_optimization.validate_data_directory",
            return_value=partial_validations(),
        ), patch("swing_trade_bot.run_optimization.load_market_data", return_value={}), patch(
            "swing_trade_bot.run_optimization.StrategyOptimizer"
        ) as optimizer_class, patch("swing_trade_bot.run_optimization.write_outputs"):
            optimizer_class.return_value.optimize.return_value = (best, ranked)

            report = run_optimization_report(
                Path("data"),
                Path("results"),
                account_value=100_000.0,
                allow_partial=True,
            )

        self.assertEqual(report.optimized_symbols, ("SOXL", "TQQQ", "IONL"))
        self.assertEqual(set(report.skipped_symbols), {"BEX", "IRE", "DRAM"})
        self.assertIn("insufficient rows", report.skipped_symbols["BEX"])
        config = optimizer_class.call_args.kwargs["config"]
        self.assertEqual(config.symbols, ("SOXL", "TQQQ", "IONL"))

    def test_allow_partial_still_fails_if_spy_is_invalid(self) -> None:
        validations = partial_validations()
        validations[-2] = SymbolValidation(
            symbol="SPY",
            path=Path("data/SPY.csv"),
            exists=True,
            row_count=100,
            invalid_rows=("file: expected at least 252 rows, found 100",),
        )
        with patch("swing_trade_bot.run_optimization.validate_data_directory", return_value=validations):
            with self.assertRaises(ValueError) as raised:
                run_optimization_report(
                    Path("data"),
                    Path("results"),
                    account_value=100_000.0,
                    allow_partial=True,
                )

        self.assertIn("Benchmark data validation failed for SPY", str(raised.exception))

    def test_optimizer_runs_with_reduced_symbol_list(self) -> None:
        best = [optimization_result("SOXL")]
        ranked = best
        with patch(
            "swing_trade_bot.run_optimization.validate_data_directory",
            return_value=partial_validations(),
        ), patch("swing_trade_bot.run_optimization.load_market_data", return_value={}) as load_data, patch(
            "swing_trade_bot.run_optimization.StrategyOptimizer"
        ) as optimizer_class, patch("swing_trade_bot.run_optimization.write_outputs"):
            optimizer_class.return_value.optimize.return_value = (best, ranked)

            run_optimization(
                Path("data"),
                Path("results"),
                account_value=100_000.0,
                allow_partial=True,
            )

        load_data.assert_called_once_with(Path("data"), ("SOXL", "TQQQ", "IONL", "SPY", "QQQ"))
        self.assertEqual(
            optimizer_class.call_args.kwargs["config"].symbols,
            ("SOXL", "TQQQ", "IONL"),
        )

    def test_live_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_optimization(
                Path("data"),
                Path("results"),
                account_value=100_000.0,
                paper_trade_mode=False,
            )

    def test_summary_contains_requested_metrics(self) -> None:
        summary = format_optimization_summary([optimization_result("SOXL")])

        self.assertIn("Symbol", summary)
        self.assertIn("Score", summary)
        self.assertIn("Return", summary)
        self.assertIn("CAGR", summary)
        self.assertIn("Sharpe", summary)
        self.assertIn("Profit", summary)
        self.assertIn("Max DD", summary)
        self.assertIn("Trades", summary)
        self.assertIn("SOXL", summary)
        self.assertIn("0.7500", summary)


def optimization_result(symbol: str):
    from swing_trade_bot.optimizer import OptimizationResult

    return OptimizationResult(
        symbol=symbol,
        rank=1,
        total_return=12.5,
        cagr=6.25,
        sharpe_ratio=1.2,
        win_rate=60.0,
        profit_factor=2.5,
        max_drawdown=8.0,
        number_of_trades=5,
        parameters=ParameterSet(
            initial_stop=0.10,
            break_even_trigger=0.15,
            trailing_one_trigger=0.20,
            trailing_one_distance=0.05,
            trailing_two_trigger=0.30,
            trailing_two_distance=0.10,
            rsi_entry_min=45.0,
            rsi_entry_max=65.0,
        ),
        score=0.75,
    )


def partial_validations() -> list[SymbolValidation]:
    return [
        valid_symbol("SOXL"),
        invalid_symbol("BEX", 150),
        valid_symbol("TQQQ"),
        invalid_symbol("IRE", 167),
        valid_symbol("IONL"),
        invalid_symbol("DRAM", 55),
        valid_symbol("SPY"),
        valid_symbol("QQQ"),
    ]


def valid_symbol(symbol: str) -> SymbolValidation:
    return SymbolValidation(
        symbol=symbol,
        path=Path(f"data/{symbol}.csv"),
        exists=True,
        row_count=252,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 9, 9),
    )


def invalid_symbol(symbol: str, rows: int) -> SymbolValidation:
    return SymbolValidation(
        symbol=symbol,
        path=Path(f"data/{symbol}.csv"),
        exists=True,
        row_count=rows,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 9, 9),
        invalid_rows=(f"file: expected at least 252 rows, found {rows}",),
    )


if __name__ == "__main__":
    unittest.main()

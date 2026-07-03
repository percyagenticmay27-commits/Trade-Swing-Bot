"""Validated optimization runner for the paper swing-trading strategy."""

from __future__ import annotations

import argparse
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .config import StrategyConfig
from .data_tools import REQUIRED_SYMBOLS, format_validation_summary, validate_data_directory
from .optimizer import OptimizationResult, StrategyOptimizer, write_outputs
from .paper_runner import load_csv
from .position_state import MarketBar


@dataclass(frozen=True, slots=True)
class OptimizationRunReport:
    """Completed optimization run metadata and results."""

    best_results: list[OptimizationResult]
    ranked_results: list[OptimizationResult]
    optimized_symbols: tuple[str, ...]
    skipped_symbols: Mapping[str, str]


def run_optimization(
    data_dir: Path,
    output_dir: Path,
    *,
    account_value: float,
    paper_trade_mode: bool = True,
    allow_partial: bool = False,
) -> tuple[list[OptimizationResult], list[OptimizationResult]]:
    """Validate historical data, optimize, and write output artifacts."""
    report = run_optimization_report(
        data_dir,
        output_dir,
        account_value=account_value,
        paper_trade_mode=paper_trade_mode,
        allow_partial=allow_partial,
    )
    return report.best_results, report.ranked_results


def run_optimization_report(
    data_dir: Path,
    output_dir: Path,
    *,
    account_value: float,
    paper_trade_mode: bool = True,
    allow_partial: bool = False,
) -> OptimizationRunReport:
    """Validate data, optionally skip invalid trade symbols, and optimize."""
    if not paper_trade_mode:
        raise ValueError("Optimization runner requires paper_trade_mode=True")
    validations = validate_data_directory(data_dir)
    validation_by_symbol = {result.symbol: result for result in validations}
    if not allow_partial and not all(result.is_valid for result in validations):
        raise ValueError(
            "Data validation failed. Fix historical CSV files before optimization.\n"
            f"{format_validation_summary(validations)}"
        )

    trade_symbols = StrategyConfig().symbols
    skipped_symbols: dict[str, str] = {}
    if allow_partial:
        for benchmark in ("SPY", "QQQ"):
            if not validation_by_symbol.get(benchmark) or not validation_by_symbol[benchmark].is_valid:
                raise ValueError(
                    f"Benchmark data validation failed for {benchmark}; partial optimization cannot continue.\n"
                    f"{format_validation_summary(validations)}"
                )
        optimized_symbols = tuple(
            symbol
            for symbol in trade_symbols
            if validation_by_symbol.get(symbol) and validation_by_symbol[symbol].is_valid
        )
        skipped_symbols = {
            symbol: _skip_reason(validation_by_symbol[symbol])
            for symbol in trade_symbols
            if symbol not in optimized_symbols
        }
        if not optimized_symbols:
            raise ValueError(
                "No valid trade symbols are available for partial optimization.\n"
                f"{format_validation_summary(validations)}"
            )
    else:
        optimized_symbols = trade_symbols

    optimizer = StrategyOptimizer(
        config=StrategyConfig(symbols=optimized_symbols),
        account_value=account_value,
        paper_trade_mode=True,
    )
    market_data = load_market_data(data_dir, (*optimized_symbols, "SPY", "QQQ"))
    best_results, ranked_results = optimizer.optimize(market_data)
    write_outputs(output_dir, best_results, ranked_results)
    return OptimizationRunReport(
        best_results=best_results,
        ranked_results=ranked_results,
        optimized_symbols=optimized_symbols,
        skipped_symbols=skipped_symbols,
    )


def load_market_data(
    data_dir: Path,
    symbols: Sequence[str] = REQUIRED_SYMBOLS,
) -> dict[str, list[MarketBar]]:
    """Load validated CSV data for optimization symbols and benchmarks."""
    return {symbol: load_csv(data_dir / f"{symbol}.csv") for symbol in symbols}


def format_optimization_summary(results: Sequence[OptimizationResult]) -> str:
    """Render the requested per-symbol optimization summary."""
    headers = ("Symbol", "Score", "Return", "CAGR", "Sharpe", "Profit", "Max DD", "Trades")
    rows = [
        (
            result.symbol,
            f"{result.score:.4f}",
            _percent(result.total_return),
            _percent(result.cagr),
            f"{result.sharpe_ratio:.4f}",
            _number(result.profit_factor),
            _percent(result.max_drawdown),
            str(result.number_of_trades),
        )
        for result in results
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    lines = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    )
    return "\n".join(lines)


def format_symbol_selection(report: OptimizationRunReport) -> str:
    """Render optimized and skipped symbol details."""
    lines = [
        f"Optimized symbols: {', '.join(report.optimized_symbols)}",
        "Skipped symbols:",
    ]
    if report.skipped_symbols:
        lines.extend(
            f"- {symbol}: {reason}"
            for symbol, reason in report.skipped_symbols.items()
        )
    else:
        lines.append("- none")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate data and run paper strategy optimization")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--account-value", type=float, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    try:
        report = run_optimization_report(
            args.data_dir,
            args.output_dir,
            account_value=args.account_value,
            paper_trade_mode=True,
            allow_partial=args.allow_partial,
        )
    except ValueError as exc:
        print(exc)
        raise SystemExit(1) from exc

    print(format_symbol_selection(report))
    print()
    print(format_optimization_summary(report.best_results))


def _percent(value: float) -> str:
    return f"{value:.2f}%"


def _number(value: float) -> str:
    return "Infinity" if math.isinf(value) else f"{value:.4f}"


def _skip_reason(validation: object) -> str:
    invalid_rows = getattr(validation, "invalid_rows", ())
    if not invalid_rows:
        return "missing or invalid data"
    reason = "; ".join(invalid_rows)
    if "expected at least" in reason and "rows" in reason:
        return f"insufficient rows ({reason})"
    return reason


if __name__ == "__main__":
    main()

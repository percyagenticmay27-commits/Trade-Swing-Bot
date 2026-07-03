"""Per-symbol parameter grid optimization for the paper strategy."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path

from .backtester import BacktestResult, SwingTradeBacktester
from .config import StrategyConfig
from .paper_runner import load_csv
from .position_state import MarketBar


@dataclass(frozen=True, slots=True)
class OptimizationGrid:
    """Default parameter values requested for exhaustive testing."""

    initial_stops: tuple[float, ...] = (0.08, 0.10, 0.12, 0.15)
    break_even_triggers: tuple[float, ...] = (0.10, 0.15, 0.20)
    trailing_one_triggers: tuple[float, ...] = (0.15, 0.20, 0.25)
    trailing_one_distances: tuple[float, ...] = (0.05, 0.07, 0.10)
    trailing_two_triggers: tuple[float, ...] = (0.30, 0.40, 0.50)
    trailing_two_distances: tuple[float, ...] = (0.10, 0.12, 0.15)
    rsi_entry_ranges: tuple[tuple[float, float], ...] = (
        (40.0, 65.0),
        (45.0, 65.0),
        (50.0, 70.0),
    )

    def parameter_sets(self) -> Iterator["ParameterSet"]:
        values = product(
            self.initial_stops,
            self.break_even_triggers,
            self.trailing_one_triggers,
            self.trailing_one_distances,
            self.trailing_two_triggers,
            self.trailing_two_distances,
            self.rsi_entry_ranges,
        )
        for initial, break_even, trigger_one, distance_one, trigger_two, distance_two, rsi in values:
            yield ParameterSet(
                initial_stop=initial,
                break_even_trigger=break_even,
                trailing_one_trigger=trigger_one,
                trailing_one_distance=distance_one,
                trailing_two_trigger=trigger_two,
                trailing_two_distance=distance_two,
                rsi_entry_min=rsi[0],
                rsi_entry_max=rsi[1],
            )


@dataclass(frozen=True, slots=True)
class ParameterSet:
    initial_stop: float
    break_even_trigger: float
    trailing_one_trigger: float
    trailing_one_distance: float
    trailing_two_trigger: float
    trailing_two_distance: float
    rsi_entry_min: float
    rsi_entry_max: float

    def apply(self, config: StrategyConfig, symbol: str) -> StrategyConfig:
        return replace(
            config,
            symbols=(symbol,),
            initial_stop_percent=self.initial_stop,
            break_even_trigger=self.break_even_trigger,
            tight_trailing_trigger=self.trailing_one_trigger,
            tight_trailing_percent=self.trailing_one_distance,
            wide_trailing_trigger=self.trailing_two_trigger,
            wide_trailing_percent=self.trailing_two_distance,
            entry_rsi_min=self.rsi_entry_min,
            entry_rsi_max=self.rsi_entry_max,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "initial_stop": self.initial_stop,
            "break_even_trigger": self.break_even_trigger,
            "trailing_one_trigger": self.trailing_one_trigger,
            "trailing_one_distance": self.trailing_one_distance,
            "trailing_two_trigger": self.trailing_two_trigger,
            "trailing_two_distance": self.trailing_two_distance,
            "rsi_entry_min": self.rsi_entry_min,
            "rsi_entry_max": self.rsi_entry_max,
        }


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    symbol: str
    rank: int
    total_return: float
    cagr: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    number_of_trades: int
    parameters: ParameterSet
    score: float = 0.0
    normalized_return: float = 0.0
    normalized_sharpe: float = 0.0
    normalized_profit_factor: float = 0.0
    normalized_win_rate: float = 0.0
    normalized_drawdown: float = 0.0

    def ranked_row(self) -> dict[str, object]:
        row: dict[str, object] = {
            "symbol": self.symbol,
            "rank": self.rank,
            "total_return": self.total_return,
            "cagr": self.cagr,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "profit_factor": _serializable_number(self.profit_factor),
            "max_drawdown": self.max_drawdown,
            "number_of_trades": self.number_of_trades,
            "score": self.score,
            "normalized_return": self.normalized_return,
            "normalized_sharpe": self.normalized_sharpe,
            "normalized_profit_factor": self.normalized_profit_factor,
            "normalized_win_rate": self.normalized_win_rate,
            "normalized_drawdown": self.normalized_drawdown,
        }
        row.update(self.parameters.to_dict())
        return row

    def best_row(self) -> dict[str, object]:
        row: dict[str, object] = {
            "symbol": self.symbol,
            "best_total_return": self.total_return,
            "best_cagr": self.cagr,
            "best_sharpe_ratio": self.sharpe_ratio,
            "best_win_rate": self.win_rate,
            "best_profit_factor": _serializable_number(self.profit_factor),
            "max_drawdown": self.max_drawdown,
            "number_of_trades": self.number_of_trades,
            "score": self.score,
            "normalized_return": self.normalized_return,
            "normalized_sharpe": self.normalized_sharpe,
            "normalized_profit_factor": self.normalized_profit_factor,
            "normalized_win_rate": self.normalized_win_rate,
            "normalized_drawdown": self.normalized_drawdown,
        }
        row.update(self.parameters.to_dict())
        return row

    def json_result(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "best_total_return": self.total_return,
            "best_cagr": self.cagr,
            "best_sharpe_ratio": self.sharpe_ratio,
            "best_win_rate": self.win_rate,
            "best_profit_factor": _serializable_number(self.profit_factor),
            "max_drawdown": self.max_drawdown,
            "number_of_trades": self.number_of_trades,
            "score": self.score,
            "normalized_return": self.normalized_return,
            "normalized_sharpe": self.normalized_sharpe,
            "normalized_profit_factor": self.normalized_profit_factor,
            "normalized_win_rate": self.normalized_win_rate,
            "normalized_drawdown": self.normalized_drawdown,
            "parameter_set": self.parameters.to_dict(),
        }


class StrategyOptimizer:
    """Exhaustively rank strategy settings for each ticker independently."""

    def __init__(
        self,
        config: StrategyConfig | None = None,
        *,
        grid: OptimizationGrid | None = None,
        account_value: float = 100_000.0,
        paper_trade_mode: bool = True,
    ) -> None:
        if not paper_trade_mode:
            raise ValueError("Optimization requires paper_trade_mode=True")
        if account_value <= 0:
            raise ValueError("account_value must be positive")
        self.config = config or StrategyConfig()
        self.grid = grid or OptimizationGrid()
        self.account_value = account_value
        self.paper_trade_mode = paper_trade_mode

    def optimize(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
    ) -> tuple[list[OptimizationResult], list[OptimizationResult]]:
        """Return the best row per symbol and every ranked combination."""
        normalized = {symbol.upper(): list(bars) for symbol, bars in market_data.items()}
        best_results: list[OptimizationResult] = []
        all_ranked: list[OptimizationResult] = []
        for symbol in self.config.symbols:
            if symbol not in normalized:
                raise ValueError(f"Missing market data for: {symbol}")
            evaluated = [
                self._evaluate(symbol, parameters, normalized)
                for parameters in self.grid.parameter_sets()
            ]
            evaluated = _normalize_and_score(evaluated)
            evaluated.sort(
                key=lambda result: (
                    result.score,
                    result.total_return,
                    result.sharpe_ratio,
                    -result.max_drawdown,
                ),
                reverse=True,
            )
            ranked = [replace(result, rank=index) for index, result in enumerate(evaluated, 1)]
            best_results.append(ranked[0])
            all_ranked.extend(ranked)
        return best_results, all_ranked

    def _evaluate(
        self,
        symbol: str,
        parameters: ParameterSet,
        market_data: Mapping[str, list[MarketBar]],
    ) -> OptimizationResult:
        config = parameters.apply(self.config, symbol)
        result = SwingTradeBacktester(
            config,
            account_value=self.account_value,
            paper_trade_mode=True,
        ).run(market_data)[0]
        return OptimizationResult(
            symbol=symbol,
            rank=0,
            total_return=result.total_return,
            cagr=_cagr(result, market_data[symbol], config),
            sharpe_ratio=_sharpe_ratio(result.equity_curve),
            win_rate=result.win_rate,
            profit_factor=_profit_factor(result),
            max_drawdown=result.max_drawdown,
            number_of_trades=result.number_of_trades,
            parameters=parameters,
        )


def write_outputs(
    output_dir: Path,
    best_results: Sequence[OptimizationResult],
    ranked_results: Sequence[OptimizationResult],
) -> tuple[Path, ...]:
    """Write summary, ranking, and metric-specific optimizer artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results_csv = output_dir / "results.csv"
    results_json = output_dir / "results.json"
    ranked_csv = output_dir / "ranked_results.csv"
    best_return_csv = output_dir / "best_by_return.csv"
    best_sharpe_csv = output_dir / "best_by_sharpe.csv"
    best_drawdown_csv = output_dir / "best_by_drawdown.csv"
    best_score_csv = output_dir / "best_by_score.csv"
    _write_csv(results_csv, [result.best_row() for result in best_results])
    _write_csv(ranked_csv, [result.ranked_row() for result in ranked_results])
    by_symbol = {
        result.symbol: [row for row in ranked_results if row.symbol == result.symbol]
        for result in best_results
    }
    _write_csv(
        best_return_csv,
        [max(rows, key=lambda row: row.total_return).ranked_row() for rows in by_symbol.values()],
    )
    _write_csv(
        best_sharpe_csv,
        [max(rows, key=lambda row: row.sharpe_ratio).ranked_row() for rows in by_symbol.values()],
    )
    _write_csv(
        best_drawdown_csv,
        [min(rows, key=lambda row: row.max_drawdown).ranked_row() for rows in by_symbol.values()],
    )
    _write_csv(best_score_csv, [result.ranked_row() for result in best_results])
    payload = {
        "paper_trade_mode": True,
        "ranking_method": (
            "0.35 normalized return + 0.25 normalized Sharpe + "
            "0.20 normalized profit factor + 0.10 normalized win rate - "
            "0.10 normalized max drawdown"
        ),
        "combinations_per_symbol": len(ranked_results) // len(best_results),
        "results": [result.json_result() for result in best_results],
    }
    results_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return (
        results_csv,
        results_json,
        ranked_csv,
        best_return_csv,
        best_sharpe_csv,
        best_drawdown_csv,
        best_score_csv,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize paper swing strategy parameters")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path.cwd())
    parser.add_argument("--account-value", type=float, required=True)
    args = parser.parse_args()

    optimizer = StrategyOptimizer(account_value=args.account_value)
    required_symbols = (*optimizer.config.symbols, "SPY", "QQQ")
    market_data = {
        symbol: load_csv(args.data_dir / f"{symbol}.csv")
        for symbol in required_symbols
    }
    best, ranked = optimizer.optimize(market_data)
    for path in write_outputs(args.output_dir, best, ranked):
        print(path)


def _cagr(result: BacktestResult, bars: Sequence[MarketBar], config: StrategyConfig) -> float:
    required = max(config.ema_period, config.sma_period, config.rsi_period + 1, config.volume_period + 1)
    days = max((bars[-1].date - bars[required - 1].date).days, 1)
    years = days / 365.25
    growth = result.ending_account_value / result.starting_account_value
    return ((growth ** (1.0 / years)) - 1.0) * 100.0 if growth > 0 else -100.0


def _sharpe_ratio(equity_curve: Sequence[float]) -> float:
    returns = [
        (current / previous) - 1.0
        for previous, current in zip(equity_curve, equity_curve[1:])
        if previous > 0
    ]
    if not returns:
        return 0.0
    average = sum(returns) / len(returns)
    variance = sum((value - average) ** 2 for value in returns) / len(returns)
    standard_deviation = math.sqrt(variance)
    return 0.0 if standard_deviation == 0 else (average / standard_deviation) * math.sqrt(252.0)


def _profit_factor(result: BacktestResult) -> float:
    gains = sum(trade.profit_loss for trade in result.trades if trade.profit_loss > 0)
    losses = -sum(trade.profit_loss for trade in result.trades if trade.profit_loss < 0)
    if losses > 0:
        return gains / losses
    return math.inf if gains > 0 else 0.0


def _normalize_and_score(results: Sequence[OptimizationResult]) -> list[OptimizationResult]:
    returns = _min_max([result.total_return for result in results])
    sharpes = _min_max([result.sharpe_ratio for result in results])
    profit_factors = _normalize_profit_factors([result.profit_factor for result in results])
    win_rates = _min_max([result.win_rate for result in results])
    drawdowns = _min_max([result.max_drawdown for result in results])

    scored: list[OptimizationResult] = []
    for index, result in enumerate(results):
        score = (
            (0.35 * returns[index])
            + (0.25 * sharpes[index])
            + (0.20 * profit_factors[index])
            + (0.10 * win_rates[index])
            - (0.10 * drawdowns[index])
        )
        scored.append(
            replace(
                result,
                score=score,
                normalized_return=returns[index],
                normalized_sharpe=sharpes[index],
                normalized_profit_factor=profit_factors[index],
                normalized_win_rate=win_rates[index],
                normalized_drawdown=drawdowns[index],
            )
        )
    return scored


def _min_max(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return [0.0 for _ in values]
    return [(value - minimum) / (maximum - minimum) for value in values]


def _normalize_profit_factors(values: Sequence[float]) -> list[float]:
    finite_values = [value for value in values if not math.isinf(value)]
    if not finite_values:
        return [1.0 for _ in values]
    finite_scores = _min_max(finite_values)
    normalized: list[float] = []
    finite_index = 0
    for value in values:
        if math.isinf(value):
            normalized.append(1.0)
        else:
            normalized.append(finite_scores[finite_index])
            finite_index += 1
    return normalized


def _serializable_number(value: float) -> float | str:
    return "Infinity" if math.isinf(value) else value


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows available for {path.name}")
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()

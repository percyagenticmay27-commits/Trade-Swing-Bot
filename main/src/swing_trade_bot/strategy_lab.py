"""Paper-only Strategy Lab for comparing exit strategies per symbol."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from swing_trade_bot.config import StrategyConfig
from swing_trade_bot.indicators import ema, rsi, sma, volume_average
from swing_trade_bot.paper_runner import load_csv
from swing_trade_bot.position_state import MarketBar


StrategyName = Literal["Strategy A", "Strategy B"]
STRATEGY_A: StrategyName = "Strategy A"
STRATEGY_B: StrategyName = "Strategy B"
LAB_SYMBOLS = ("SOXL", "TQQQ", "NEBX", "NBIS", "IREN", "BE", "IONL", "BEX", "DRAM")
COMPARISON_COLUMNS = (
    "symbol",
    "strategy",
    "total_return",
    "cagr",
    "win_rate",
    "profit_factor",
    "max_drawdown",
    "sharpe_ratio",
    "trade_count",
    "average_gain",
    "average_loss",
)
RECOMMENDATION_COLUMNS = (
    "symbol",
    "active_strategy",
    "strategy_a_return",
    "strategy_b_return",
    "strategy_a_win_rate",
    "strategy_b_win_rate",
    "strategy_a_profit_factor",
    "strategy_b_profit_factor",
    "strategy_a_drawdown",
    "strategy_b_drawdown",
    "recommended_strategy",
    "switch_eligible",
    "months_outperforming",
)


@dataclass(frozen=True, slots=True)
class StrategyLabTrade:
    """One completed strategy-lab position lifecycle."""

    symbol: str
    strategy: StrategyName
    entry_date: date
    exit_date: date
    entry_price: float
    final_exit_price: float
    return_percent: float
    profit_loss: float


@dataclass(frozen=True, slots=True)
class StrategyLabResult:
    """Performance metrics for one symbol and one strategy."""

    symbol: str
    strategy: StrategyName
    total_return: float
    cagr: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    trade_count: int
    average_gain: float | None
    average_loss: float | None
    starting_account_value: float
    ending_account_value: float
    trades: tuple[StrategyLabTrade, ...]
    equity_curve: tuple[float, ...]

    def row(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "total_return": self.total_return,
            "cagr": self.cagr,
            "win_rate": self.win_rate,
            "profit_factor": _serializable_number(self.profit_factor),
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "trade_count": self.trade_count,
            "average_gain": "" if self.average_gain is None else self.average_gain,
            "average_loss": "" if self.average_loss is None else self.average_loss,
        }

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["profit_factor"] = _serializable_number(self.profit_factor)
        payload["trades"] = [
            {
                **asdict(trade),
                "entry_date": trade.entry_date.isoformat(),
                "exit_date": trade.exit_date.isoformat(),
            }
            for trade in self.trades
        ]
        return payload


@dataclass(frozen=True, slots=True)
class StrategyRecommendation:
    """Per-symbol strategy selection row."""

    symbol: str
    active_strategy: StrategyName
    strategy_a_return: float
    strategy_b_return: float
    strategy_a_win_rate: float
    strategy_b_win_rate: float
    strategy_a_profit_factor: float
    strategy_b_profit_factor: float
    strategy_a_drawdown: float
    strategy_b_drawdown: float
    recommended_strategy: StrategyName
    switch_eligible: bool
    months_outperforming: int

    def row(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "active_strategy": self.active_strategy,
            "strategy_a_return": self.strategy_a_return,
            "strategy_b_return": self.strategy_b_return,
            "strategy_a_win_rate": self.strategy_a_win_rate,
            "strategy_b_win_rate": self.strategy_b_win_rate,
            "strategy_a_profit_factor": _serializable_number(self.strategy_a_profit_factor),
            "strategy_b_profit_factor": _serializable_number(self.strategy_b_profit_factor),
            "strategy_a_drawdown": self.strategy_a_drawdown,
            "strategy_b_drawdown": self.strategy_b_drawdown,
            "recommended_strategy": self.recommended_strategy,
            "switch_eligible": self.switch_eligible,
            "months_outperforming": self.months_outperforming,
        }


class StrategyLab:
    """Run Strategy A and Strategy B on each symbol without live execution."""

    def __init__(
        self,
        config: StrategyConfig | None = None,
        *,
        symbols: Sequence[str] = LAB_SYMBOLS,
        account_value: float = 100_000.0,
        paper_trade_mode: bool = True,
    ) -> None:
        if not paper_trade_mode:
            raise ValueError("Strategy Lab requires paper_trade_mode=True")
        if account_value <= 0:
            raise ValueError("account_value must be positive")
        self.config = config or StrategyConfig()
        self.symbols = tuple(symbol.upper() for symbol in symbols)
        self.account_value = account_value
        self.paper_trade_mode = paper_trade_mode

    def run(self, market_data: Mapping[str, Sequence[MarketBar]]) -> list[StrategyLabResult]:
        normalized = {symbol.upper(): list(bars) for symbol, bars in market_data.items()}
        results: list[StrategyLabResult] = []
        for symbol in self.symbols:
            if symbol not in normalized:
                continue
            bars = normalized[symbol]
            _validate_bars(symbol, bars)
            results.append(_simulate_strategy(symbol, bars, STRATEGY_A, self.config, self.account_value))
            results.append(_simulate_strategy(symbol, bars, STRATEGY_B, self.config, self.account_value))
        if not results:
            raise ValueError("No requested symbols had market data")
        return results

    def recommend(
        self,
        results: Sequence[StrategyLabResult],
        *,
        active_strategies: Mapping[str, StrategyName] | None = None,
        review_history: Mapping[str, int] | None = None,
        drawdown_tolerance: float = 5.0,
    ) -> list[StrategyRecommendation]:
        by_symbol: dict[str, dict[StrategyName, StrategyLabResult]] = {}
        for result in results:
            by_symbol.setdefault(result.symbol, {})[result.strategy] = result

        recommendations: list[StrategyRecommendation] = []
        active_strategies = active_strategies or {}
        review_history = review_history or {}
        for symbol in sorted(by_symbol):
            strategy_a = by_symbol[symbol][STRATEGY_A]
            strategy_b = by_symbol[symbol][STRATEGY_B]
            months = review_history.get(symbol, 0)
            if strategy_b.total_return > strategy_a.total_return:
                months += 1
            else:
                months = 0
            switch_eligible = (
                strategy_b.total_return > strategy_a.total_return
                and months >= 3
                and strategy_b.trade_count >= 20
                and strategy_b.profit_factor >= strategy_a.profit_factor
                and strategy_b.max_drawdown <= strategy_a.max_drawdown + drawdown_tolerance
            )
            recommendations.append(
                StrategyRecommendation(
                    symbol=symbol,
                    active_strategy=active_strategies.get(symbol, STRATEGY_A),
                    strategy_a_return=strategy_a.total_return,
                    strategy_b_return=strategy_b.total_return,
                    strategy_a_win_rate=strategy_a.win_rate,
                    strategy_b_win_rate=strategy_b.win_rate,
                    strategy_a_profit_factor=strategy_a.profit_factor,
                    strategy_b_profit_factor=strategy_b.profit_factor,
                    strategy_a_drawdown=strategy_a.max_drawdown,
                    strategy_b_drawdown=strategy_b.max_drawdown,
                    recommended_strategy=STRATEGY_B if switch_eligible else STRATEGY_A,
                    switch_eligible=switch_eligible,
                    months_outperforming=months,
                )
            )
        return recommendations


def write_strategy_lab_outputs(
    output_dir: Path,
    results: Sequence[StrategyLabResult],
    recommendations: Sequence[StrategyRecommendation],
) -> tuple[Path, Path, Path]:
    """Write comparison CSV/JSON and recommendation CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_csv = output_dir / "strategy_comparison.csv"
    comparison_json = output_dir / "strategy_comparison.json"
    recommendations_csv = output_dir / "strategy_recommendations.csv"

    with comparison_csv.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=COMPARISON_COLUMNS)
        writer.writeheader()
        writer.writerows(result.row() for result in results)

    comparison_json.write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "strategies": {
                    "Strategy A": "Production trailing-stop exit model",
                    "Strategy B": "Momentum Core partial-profit exit model",
                },
                "results": [result.to_dict() for result in results],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with recommendations_csv.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=RECOMMENDATION_COLUMNS)
        writer.writeheader()
        writer.writerows(row.row() for row in recommendations)
    return comparison_csv, comparison_json, recommendations_csv


def load_review_history(path: Path | None) -> dict[str, int]:
    """Load prior consecutive Strategy B outperformance counts by symbol."""
    if path is None or not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return {
            row["symbol"].upper(): int(row.get("months_outperforming", 0))
            for row in csv.DictReader(input_file)
        }


def load_active_strategies(path: Path | None) -> dict[str, StrategyName]:
    """Load current active strategy by symbol."""
    if path is None or not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return {
            row["symbol"].upper(): _strategy_name(row.get("active_strategy", STRATEGY_A))
            for row in csv.DictReader(input_file)
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paper-only Strategy Lab")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--account-value", type=float, default=100_000.0)
    parser.add_argument("--symbols", nargs="*", default=list(LAB_SYMBOLS))
    parser.add_argument("--review-history", type=Path)
    parser.add_argument("--active-strategies", type=Path)
    args = parser.parse_args()

    lab = StrategyLab(symbols=args.symbols, account_value=args.account_value, paper_trade_mode=True)
    market_data = {
        symbol.upper(): load_csv(args.data_dir / f"{symbol.upper()}.csv")
        for symbol in args.symbols
        if (args.data_dir / f"{symbol.upper()}.csv").exists()
    }
    results = lab.run(market_data)
    recommendations = lab.recommend(
        results,
        active_strategies=load_active_strategies(args.active_strategies),
        review_history=load_review_history(args.review_history),
    )
    paths = write_strategy_lab_outputs(args.output_dir, results, recommendations)
    print(format_strategy_report(results))
    print("\nRecommendations")
    print(format_recommendations(recommendations))
    for path in paths:
        print(path)


def format_strategy_report(results: Sequence[StrategyLabResult]) -> str:
    headers = ("Symbol", "Strategy", "Return", "CAGR", "Win", "PF", "DD", "Sharpe", "Trades")
    rows = [
        (
            result.symbol,
            result.strategy,
            _percent(result.total_return),
            _percent(result.cagr),
            _percent(result.win_rate),
            _number(result.profit_factor),
            _percent(result.max_drawdown),
            f"{result.sharpe_ratio:.2f}",
            str(result.trade_count),
        )
        for result in results
    ]
    return _table(headers, rows)


def format_recommendations(recommendations: Sequence[StrategyRecommendation]) -> str:
    headers = ("Symbol", "Active", "A Return", "B Return", "Recommended", "Switch", "Months")
    rows = [
        (
            row.symbol,
            row.active_strategy,
            _percent(row.strategy_a_return),
            _percent(row.strategy_b_return),
            row.recommended_strategy,
            str(row.switch_eligible),
            str(row.months_outperforming),
        )
        for row in recommendations
    ]
    return _table(headers, rows)


@dataclass(slots=True)
class _OpenTrade:
    entry_date: date
    entry_price: float
    quantity: float
    remaining_quantity: float
    allocation: float
    realized_cash: float = 0.0
    stop_price: float | None = None
    highest_close: float = 0.0
    sold_20: bool = False
    sold_35: bool = False
    active_trail_percent: float | None = None


def _simulate_strategy(
    symbol: str,
    bars: Sequence[MarketBar],
    strategy: StrategyName,
    config: StrategyConfig,
    account_value: float,
) -> StrategyLabResult:
    required = max(config.ema_period, config.sma_period, config.rsi_period + 1, config.volume_period + 1)
    if len(bars) < required:
        raise ValueError(f"{symbol} requires at least {required} bars")
    cash = account_value
    open_trade: _OpenTrade | None = None
    pending_entry = False
    trades: list[StrategyLabTrade] = []
    equity_curve = [account_value]

    for index in range(required - 1, len(bars)):
        bar = bars[index]
        history = bars[: index + 1]
        if pending_entry and open_trade is None:
            quantity = cash / bar.open_price
            open_trade = _OpenTrade(
                entry_date=bar.date,
                entry_price=bar.open_price,
                quantity=quantity,
                remaining_quantity=quantity,
                allocation=cash,
                stop_price=bar.open_price * (1.0 - config.initial_stop_percent),
                highest_close=bar.close,
            )
            cash = 0.0
            pending_entry = False

        if open_trade is not None:
            # The active stop is known before today's close. Close-based trailing
            # updates are applied only after this intraday low check.
            if open_trade.stop_price is not None and bar.low_price <= open_trade.stop_price:
                cash += open_trade.remaining_quantity * open_trade.stop_price
                trades.append(_close_trade(symbol, strategy, open_trade, bar.date, open_trade.stop_price, cash))
                open_trade = None
                equity_curve.append(cash)
                continue
            open_trade.highest_close = max(open_trade.highest_close, bar.close)
            if strategy == STRATEGY_B:
                cash += _apply_strategy_b_partials(open_trade, bar)
            _update_trade_stops(open_trade, bar, strategy)

        if open_trade is None and not pending_entry and _entry_signal(history, config):
            pending_entry = True

        equity_curve.append(cash + (0.0 if open_trade is None else open_trade.remaining_quantity * bar.close))

    if open_trade is not None:
        final_bar = bars[-1]
        cash += open_trade.remaining_quantity * final_bar.close
        trades.append(_close_trade(symbol, strategy, open_trade, final_bar.date, final_bar.close, cash))
        equity_curve[-1] = cash

    return _build_result(symbol, strategy, bars, required, account_value, cash, trades, equity_curve)


def _entry_signal(history: Sequence[MarketBar], config: StrategyConfig) -> bool:
    closes = [bar.close for bar in history]
    volumes = [bar.volume for bar in history]
    current_ema = ema(closes, config.ema_period)
    current_sma = sma(closes, config.sma_period)
    current_rsi = rsi(closes, config.rsi_period)
    current_volume_average = volume_average(volumes[:-1], config.volume_period)
    if None in (current_ema, current_sma, current_rsi, current_volume_average):
        return False
    return (
        closes[-1] > current_ema
        and closes[-1] > current_sma
        and config.entry_rsi_min <= current_rsi <= config.entry_rsi_max
        and volumes[-1] > current_volume_average
    )


def _update_trade_stops(open_trade: _OpenTrade, bar: MarketBar, strategy: StrategyName) -> None:
    gain = (bar.close / open_trade.entry_price) - 1.0
    if strategy == STRATEGY_A:
        proposed: float | None = None
        if gain >= 0.30:
            proposed = open_trade.highest_close * 0.90
        elif gain >= 0.20:
            proposed = open_trade.highest_close * 0.95
        if proposed is not None:
            open_trade.stop_price = max(open_trade.stop_price or proposed, proposed)
        return

    if open_trade.sold_35:
        if gain >= 1.00:
            open_trade.active_trail_percent = 0.10
        elif gain >= 0.75:
            open_trade.active_trail_percent = 0.12
        else:
            open_trade.active_trail_percent = 0.15
        proposed = open_trade.highest_close * (1.0 - open_trade.active_trail_percent)
        open_trade.stop_price = max(open_trade.stop_price or proposed, proposed)


def _apply_strategy_b_partials(open_trade: _OpenTrade, bar: MarketBar) -> float:
    gain = (bar.close / open_trade.entry_price) - 1.0
    cash = 0.0
    if not open_trade.sold_20 and gain >= 0.20:
        quantity = open_trade.quantity * 0.25
        open_trade.remaining_quantity -= quantity
        open_trade.realized_cash += quantity * bar.close
        cash += quantity * bar.close
        open_trade.sold_20 = True
    if not open_trade.sold_35 and gain >= 0.35:
        quantity = open_trade.quantity * 0.25
        open_trade.remaining_quantity -= quantity
        open_trade.realized_cash += quantity * bar.close
        cash += quantity * bar.close
        open_trade.sold_35 = True
        proposed = open_trade.highest_close * 0.85
        open_trade.stop_price = max(open_trade.stop_price or proposed, proposed)
    return cash


def _close_trade(
    symbol: str,
    strategy: StrategyName,
    open_trade: _OpenTrade,
    exit_date: date,
    final_exit_price: float,
    cash_after_exit: float,
) -> StrategyLabTrade:
    profit_loss = cash_after_exit - open_trade.allocation
    return StrategyLabTrade(
        symbol=symbol,
        strategy=strategy,
        entry_date=open_trade.entry_date,
        exit_date=exit_date,
        entry_price=open_trade.entry_price,
        final_exit_price=final_exit_price,
        return_percent=(profit_loss / open_trade.allocation) * 100.0,
        profit_loss=profit_loss,
    )


def _build_result(
    symbol: str,
    strategy: StrategyName,
    bars: Sequence[MarketBar],
    required: int,
    starting_account_value: float,
    ending_account_value: float,
    trades: Sequence[StrategyLabTrade],
    equity_curve: Sequence[float],
) -> StrategyLabResult:
    returns = [trade.return_percent for trade in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    days = max((bars[-1].date - bars[required - 1].date).days, 1)
    years = days / 365.25
    growth = ending_account_value / starting_account_value
    return StrategyLabResult(
        symbol=symbol,
        strategy=strategy,
        total_return=((ending_account_value / starting_account_value) - 1.0) * 100.0,
        cagr=((growth ** (1.0 / years)) - 1.0) * 100.0 if growth > 0 else -100.0,
        win_rate=(len(wins) / len(trades) * 100.0) if trades else 0.0,
        profit_factor=_profit_factor(trades),
        max_drawdown=_max_drawdown(equity_curve),
        sharpe_ratio=_sharpe_ratio(equity_curve),
        trade_count=len(trades),
        average_gain=_average(wins),
        average_loss=_average(losses),
        starting_account_value=starting_account_value,
        ending_account_value=ending_account_value,
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
    )


def _profit_factor(trades: Sequence[StrategyLabTrade]) -> float:
    gains = sum(trade.profit_loss for trade in trades if trade.profit_loss > 0)
    losses = -sum(trade.profit_loss for trade in trades if trade.profit_loss < 0)
    if losses > 0:
        return gains / losses
    return math.inf if gains > 0 else 0.0


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0]
    drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = max(drawdown, ((peak - equity) / peak) * 100.0)
    return drawdown


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


def _validate_bars(symbol: str, bars: Sequence[MarketBar]) -> None:
    if any(left.date >= right.date for left, right in zip(bars, bars[1:])):
        raise ValueError(f"{symbol} bars must be strictly chronological")


def _strategy_name(value: str) -> StrategyName:
    normalized = value.strip().upper().replace("_", " ")
    if normalized in {"B", "STRATEGY B"}:
        return STRATEGY_B
    return STRATEGY_A


def _average(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _serializable_number(value: float) -> float | str:
    return "Infinity" if math.isinf(value) else value


def _number(value: float) -> str:
    return "Infinity" if math.isinf(value) else f"{value:.2f}"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        return ""
    widths = [max(len(headers[index]), *(len(row[index]) for row in rows)) for index in range(len(headers))]
    lines = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows)
    return "\n".join(lines)


if __name__ == "__main__":
    main()

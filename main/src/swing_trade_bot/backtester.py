"""Day-by-day backtesting for the paper swing-trading strategy."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path

from .config import StrategyConfig
from .engine import SwingTradeEngine
from .paper_runner import load_csv
from .position_state import MarketBar, PositionState


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """One completed paper trade."""

    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    return_percent: float
    profit_loss: float
    holding_period: int
    exit_reason: str


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Performance metrics for one independently backtested ticker."""

    symbol: str
    total_return: float
    buy_and_hold_return: float
    number_of_trades: int
    win_rate: float
    average_win: float | None
    average_loss: float | None
    max_drawdown: float
    best_trade: float | None
    worst_trade: float | None
    average_holding_period: float | None
    starting_account_value: float
    ending_account_value: float
    trades: tuple[TradeRecord, ...]
    equity_curve: tuple[float, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable result."""
        result = asdict(self)
        result.pop("equity_curve")
        for trade in result["trades"]:  # type: ignore[index]
            trade["entry_date"] = trade["entry_date"].isoformat()
            trade["exit_date"] = trade["exit_date"].isoformat()
        return result


class SwingTradeBacktester:
    """Run the existing paper engine over rolling historical CSV bars."""

    def __init__(
        self,
        config: StrategyConfig | None = None,
        *,
        account_value: float = 100_000.0,
        paper_trade_mode: bool = True,
    ) -> None:
        if not paper_trade_mode:
            raise ValueError("Backtesting requires paper_trade_mode=True")
        if account_value <= 0:
            raise ValueError("account_value must be positive")
        self.config = config or StrategyConfig()
        self.account_value = account_value
        self.paper_trade_mode = paper_trade_mode

    def run(self, market_data: Mapping[str, Sequence[MarketBar]]) -> list[BacktestResult]:
        """Backtest each configured ticker independently."""
        normalized = {symbol.upper(): list(bars) for symbol, bars in market_data.items()}
        missing = [symbol for symbol in self.config.symbols if symbol not in normalized]
        if missing:
            raise ValueError(f"Missing market data for: {', '.join(missing)}")
        for symbol, bars in normalized.items():
            _validate_bars(symbol, bars)
        return [self._run_symbol(symbol, normalized) for symbol in self.config.symbols]

    def _run_symbol(
        self,
        symbol: str,
        market_data: Mapping[str, list[MarketBar]],
    ) -> BacktestResult:
        bars = market_data[symbol]
        required = max(
            self.config.ema_period,
            self.config.sma_period,
            self.config.rsi_period + 1,
            self.config.volume_period + 1,
        )
        if len(bars) < required:
            raise ValueError(f"{symbol} requires at least {required} daily bars")

        engine = SwingTradeEngine(
            replace(self.config, symbols=(symbol,)),
            account_value=self.account_value,
            paper_trade_mode=True,
        )
        cash = self.account_value
        shares = 0.0
        entry_date: date | None = None
        entry_price: float | None = None
        entry_index: int | None = None
        pending_allocation: float | None = None
        trades: list[TradeRecord] = []
        equity_curve = [self.account_value]

        for index in range(required - 1, len(bars)):
            bar = bars[index]
            history = bars[: index + 1]

            # A BUY is known only after the prior close and fills at today's open.
            if pending_allocation is not None and shares == 0:
                allocation = min(pending_allocation, cash)
                shares = allocation / bar.open_price
                cash -= allocation
                entry_date = bar.date
                entry_price = bar.open_price
                entry_index = index
                engine._open_position(engine.positions[symbol], bar.open_price)
                pending_allocation = None

            # The carried stop is known before today's close, so checking the low
            # here does not use a stop calculated from future closing information.
            state = engine.positions[symbol]
            if shares > 0 and state.current_stop is not None and bar.low_price <= state.current_stop:
                stop_price = state.current_stop
                cash += shares * stop_price
                trades.append(
                    _trade_record(
                        entry_date,
                        bar.date,
                        entry_price,
                        stop_price,
                        entry_index,
                        index,
                        shares,
                        "Intraday low reached the active stop",
                    )
                )
                shares = 0.0
                entry_date = None
                entry_price = None
                entry_index = None
                _close_engine_position(state, stop_price)
                equity_curve.append(cash)
                continue

            benchmarks = {
                benchmark: _bars_through_date(benchmark_bars, bar.date)
                for benchmark, benchmark_bars in market_data.items()
                if benchmark in {"SPY", "QQQ"}
            }
            signal = engine.evaluate(symbol, history, benchmarks)

            if signal.signal == "BUY" and shares == 0:
                pending_allocation = signal.suggested_position_size or 0.0
                _defer_engine_entry(engine.positions[symbol])
            elif signal.signal == "SELL" and shares > 0:
                cash += shares * bar.close
                trades.append(
                    _trade_record(
                        entry_date,
                        bar.date,
                        entry_price,
                        bar.close,
                        entry_index,
                        index,
                        shares,
                        signal.reason,
                    )
                )
                shares = 0.0
                entry_date = None
                entry_price = None
                entry_index = None
                _close_engine_position(engine.positions[symbol], bar.close)

            equity_curve.append(cash + shares * bar.close)

        if shares > 0:
            final_bar = bars[-1]
            cash += shares * final_bar.close
            trades.append(
                _trade_record(
                    entry_date,
                    final_bar.date,
                    entry_price,
                    final_bar.close,
                    entry_index,
                    len(bars) - 1,
                    shares,
                    "End-of-backtest liquidation",
                )
            )
            equity_curve[-1] = cash

        first_price = bars[required - 1].close
        buy_and_hold = ((bars[-1].close / first_price) - 1.0) * 100.0
        returns = [trade.return_percent for trade in trades]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        return BacktestResult(
            symbol=symbol,
            total_return=((cash / self.account_value) - 1.0) * 100.0,
            buy_and_hold_return=buy_and_hold,
            number_of_trades=len(trades),
            win_rate=(len(wins) / len(trades) * 100.0) if trades else 0.0,
            average_win=_average(wins),
            average_loss=_average(losses),
            max_drawdown=_max_drawdown(equity_curve),
            best_trade=max(returns) if returns else None,
            worst_trade=min(returns) if returns else None,
            average_holding_period=_average(
                [float(trade.holding_period) for trade in trades]
            ),
            starting_account_value=self.account_value,
            ending_account_value=cash,
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
        )


def format_table(results: Sequence[BacktestResult]) -> str:
    """Render a readable fixed-width performance table."""
    headers = (
        "Symbol", "Return", "Buy/Hold", "Trades", "Win Rate", "Avg Win",
        "Avg Loss", "Max DD", "Best", "Worst", "Avg Hold",
    )
    rows = [
        (
            result.symbol,
            _percent(result.total_return),
            _percent(result.buy_and_hold_return),
            str(result.number_of_trades),
            _percent(result.win_rate),
            _percent(result.average_win),
            _percent(result.average_loss),
            _percent(result.max_drawdown),
            _percent(result.best_trade),
            _percent(result.worst_trade),
            "-" if result.average_holding_period is None else f"{result.average_holding_period:.1f}",
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


def results_to_json(results: Sequence[BacktestResult]) -> str:
    """Render backtest results as formatted JSON."""
    payload = {"paper_trade_mode": True, "results": [result.to_dict() for result in results]}
    return json.dumps(payload, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the paper swing strategy")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--account-value", type=float, required=True)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    backtester = SwingTradeBacktester(account_value=args.account_value)
    required_symbols = (*backtester.config.symbols, "SPY", "QQQ")
    market_data = {
        symbol: load_csv(args.data_dir / f"{symbol}.csv")
        for symbol in required_symbols
    }
    results = backtester.run(market_data)
    json_output = results_to_json(results)
    print(format_table(results))
    print("\nJSON\n")
    print(json_output)
    if args.json_output:
        args.json_output.write_text(json_output + "\n", encoding="utf-8")


def _trade_record(
    entry_date: date | None,
    exit_date: date,
    entry_price: float | None,
    exit_price: float,
    entry_index: int | None,
    exit_index: int,
    shares: float,
    exit_reason: str,
) -> TradeRecord:
    assert entry_date is not None and entry_price is not None and entry_index is not None
    return TradeRecord(
        entry_date=entry_date,
        exit_date=exit_date,
        entry_price=entry_price,
        exit_price=exit_price,
        return_percent=((exit_price / entry_price) - 1.0) * 100.0,
        profit_loss=shares * (exit_price - entry_price),
        holding_period=exit_index - entry_index,
        exit_reason=exit_reason,
    )


def _defer_engine_entry(state: PositionState) -> None:
    """Undo the engine's close-time paper fill until the next bar opens."""
    state.is_open = False
    state.entry_price = None
    state.highest_close = None
    state.current_stop = None
    state.position_size = None


def _close_engine_position(state: PositionState, exit_price: float) -> None:
    """Fully close engine paper state after any backtest exit."""
    state.is_open = False
    state.awaiting_reentry = True
    state.last_exit_price = exit_price
    state.entry_price = None
    state.highest_close = None
    state.current_stop = None
    state.position_size = None


def _bars_through_date(bars: Sequence[MarketBar], through: date) -> list[MarketBar]:
    return [bar for bar in bars if bar.date <= through]


def _validate_bars(symbol: str, bars: Sequence[MarketBar]) -> None:
    if any(left.date >= right.date for left, right in zip(bars, bars[1:])):
        raise ValueError(f"{symbol} bars must be strictly chronological")


def _average(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0]
    maximum = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        maximum = max(maximum, ((peak - equity) / peak) * 100.0)
    return maximum


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


if __name__ == "__main__":
    main()

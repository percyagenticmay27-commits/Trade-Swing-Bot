# Swing Trade Bot

A dependency-free Python engine for paper swing trading `SOXL`, `BEX`, `TQQQ`,
`IRE`, `IONL`, and `DRAM`. Live order placement is deliberately disabled.

## Strategy

Initial entries require price above EMA(20) and SMA(50), Wilder RSI(14) from 45
through 65, and current volume above the prior 20 completed bars' average. Every
buy also requires SPY above SMA(50); SOXL and TQQQ additionally require QQQ above
SMA(50).

The initial stop is 10% below entry. Peak profit of 15% moves it to break-even,
20% activates a 5% trail from the highest close, and 30% changes that trail to
10%. A completed close below the active stop emits `SELL`. Re-entry waits for a
price within 2% of EMA(20), RSI below 55, price above SMA(50), and passing market
filters.

## Position sizing

`suggested_position_size` is a dollar notional, not a share count:

```text
account_value * 0.01 / stop_loss_percent
```

It is capped at 20% of account value. With the default 10% stop, the allocation is
10% of account value.

## Install and test

Python 3.10 or newer is required.

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Run the paper strategy

Create one CSV per symbol in a data directory: the six strategy tickers plus
`SPY.csv` and `QQQ.csv`. Each file needs at least 51 chronological completed daily
bars. Full OHLCV headers are preferred:

```csv
date,open,high,low,close,volume
2026-01-02,99.50,101.00,99.25,100.25,1234567
```

Legacy `date,close,volume` files remain supported; their open, high, and low all
fall back to the close.

Run:

```powershell
python -m swing_trade_bot.paper_runner --data-dir .\data --account-value 100000
```

The command prints JSON containing `signal`, `reason`, `entry_price`,
`current_price`, `highest_price_since_entry`, `stop_price`,
`unrealized_gain_loss_percent`, and `suggested_position_size` for every ticker.

## Run a backtest

The backtester consumes the same eight CSV files and evaluates each strategy
ticker independently, one completed daily bar at a time:

```powershell
python -m swing_trade_bot.backtester `
  --data-dir .\data `
  --account-value 100000 `
  --json-output .\backtest-results.json
```

It prints a readable table and JSON with total return, completed trades, win rate,
average win/loss, maximum drawdown, best/worst trade, average holding period, and
the comparable buy-and-hold return. An open position is liquidated at the final
close so all trade statistics are complete. Holding periods count daily bars.

## Optimize parameters

Run the requested 2,916 parameter combinations independently for each of the six
strategy symbols:

```powershell
python -m swing_trade_bot.optimizer `
  --data-dir .\data `
  --output-dir .\optimization-results `
  --account-value 100000
```

This creates `results.csv` and `results.json` with the best setting per symbol,
plus `ranked_results.csv` containing every combination. Rankings use total return
first, then Sharpe ratio, then lower maximum drawdown. CAGR is annualized over the
evaluable backtest window, Sharpe uses daily marked-to-market equity changes with
zero risk-free rate, and profit factor uses completed trade percentage gains and
losses. A profitable run with no losing trades reports profit factor `Infinity`.

## Assumptions and limits

- Input rows are completed daily bars, sorted oldest to newest; no intraday stops.
- EMA uses an SMA seed and all subsequent observations. RSI uses Wilder smoothing.
- At +30%, the 10% trail becomes the active formula, but the stored stop is the
  maximum of the existing and proposed stops. An open position's stop never falls.
- Paper state is in memory and resets each process run. There is no persistence,
  live market-data source, slippage model, commissions, or Robinhood connection.
- `review_order` is a placeholder and `place_order` always raises an error.

## Opportunity Quality Engine

`opportunity_quality_engine.py` is the Version 1.2 single source of truth for Opportunity Quality. It scores opportunity attractiveness independently from entry timing using frozen QA weights:

- Fundamental Analysis Score: 20%
- Market Intelligence Score: 20%
- Conviction Score: 20%
- Momentum Score: 15%
- Technical Analysis Score: 15%
- Market Regime Support Score: 5%
- Portfolio Risk Adjustment Score: 5%

Missing evidence equals 0. Entry Score is display-only inside this module and does not affect Opportunity Quality.

## Executive Dashboard

`executive_dashboard.py` reads existing project outputs only and writes:

- `results/executive_dashboard.json`
- `results/executive_dashboard.md`

It summarizes allocation, SGOV reserve, active positions, confidence, watchlist state, risk flags, warnings, and suggested paper-only review actions.

## Allocation rank meaning

Opportunity rank determines how much capital or percentage allocation an eligible opportunity receives, subject to confidence caps, max position limits, theme concentration limits, and SGOV reserve handling.

## Additional summary reports

The project also includes standalone report writers for:

- `earnings_report.py`
- `discovery_summary_reports.py`

These produce paper-only earnings, theme momentum, and source confluence outputs for dashboard visibility.

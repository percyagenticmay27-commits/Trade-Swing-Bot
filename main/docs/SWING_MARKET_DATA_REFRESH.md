# Swing Market Data Refresh

## Purpose

Prepare provider-isolated completed daily OHLCV files for the paper-only Swing Bot before the existing paper runner executes.

## Safety

- `paper_trade_mode=True`
- `live_trading_enabled=False`
- `broker_execution_enabled=False`
- no brokerage imports or order placement
- the Swing Bot owns and publishes its own market data
- the AI CIO does not supply, change, or own market data

## Provider

Version 1 uses `YFINANCE`. All provider-specific code is isolated in:

```text
src/swing_trade_bot/providers/yfinance_provider.py
```

The refresh coordinator depends only on the `MarketDataProvider` protocol, so a future provider can replace YFINANCE without changing CSV publication or validation rules.

## Symbol Resolution

Required symbols:

- `SPY`
- `QQQ`
- `configured_strategy_symbols`
- current paper `portfolio_symbols`

Optional symbols:

- `watchlist_symbols`
- `candidate_symbols`

Symbols are normalized to uppercase and deduplicated. Required status always wins when a symbol appears in multiple groups.

## CSV Contract

One file is written for each usable symbol:

```text
data/<SYMBOL>.csv
```

Stable header:

```csv
Date,Open,High,Low,Close,Adj Close,Volume
```

Rows are sorted oldest to newest, duplicate dates are removed, conflicting duplicates are rejected, and current-day data is excluded until market close plus the configured settlement buffer. `Adj Close` is retained but does not replace `Close` in existing strategy calculations.

The refresh target is at least 250 completed daily bars. Files with 51–249 valid bars remain compatible with the current runner but generate warnings. Fewer than 51 bars fails validation.

## Atomic Publishing

Each candidate file is written to a sibling `.tmp` path, flushed, fsynced, re-read, validated, and then published with `os.replace`. A failed refresh never deletes or partially overwrites a prior valid CSV. A prior file is usable only when it remains valid and within the configured freshness limit.

## Separate Status Dimensions

Every symbol result records:

- fetch status
- validation status
- publication status

A successful provider response is not a successful refresh until validation and publication succeed, or a prior valid fresh file is explicitly preserved.

## Status Outputs

```text
results/market_data_refresh_status.json
results/market_data_refresh_status.md
```

Overall status:

- `READY`: all symbols succeeded without warnings
- `READY_WITH_WARNINGS`: all required symbols are usable but an optional symbol failed or another warning exists
- `BLOCKED`: any required symbol is unusable

## Command

```bash
python -m swing_trade_bot.market_data_refresh \
  --config configs/swing_market_data.json
```

Exit codes:

- `0`: `READY` or `READY_WITH_WARNINGS`
- `1`: `BLOCKED`

No scheduling, timers, persistence, broker execution, or AI CIO modification is included in this phase.

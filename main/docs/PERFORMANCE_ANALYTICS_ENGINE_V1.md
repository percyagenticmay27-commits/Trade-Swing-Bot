# Performance Analytics Engine Version 1

## Purpose

The Performance Analytics Engine converts authoritative paper-ledger evidence
into strategy performance metrics. It reads only outputs from the Paper
Portfolio Manager and Trade History Manager.

It does not fetch market data, make trade decisions, place orders, move capital,
or write to a database.

## Inputs

- `results/paper_ledger/paper_portfolio_summary.json`
- `results/paper_ledger/closed_positions.json`
- `results/paper_ledger/trade_history_summary.json`

## Outputs

- `results/paper_ledger/paper_performance.json`
- `results/paper_ledger/paper_performance.csv`
- `results/paper_ledger/paper_performance.md`

All outputs use atomic replacement.

## Metrics

Version 1 publishes:

- account capital
- portfolio value
- cash balance
- invested capital
- open-position count
- total trade events
- closed-trade count
- wins, losses, and breakeven trades
- win rate
- realized, unrealized, and total P/L
- portfolio return percentage
- gross profit and gross loss
- profit factor
- average gain and average loss
- average trade P/L
- largest win and largest loss
- average holding period
- per-strategy closed-trade performance

## Evidence rules

Missing closed trades do not produce fabricated zeros for win rate, average
trade metrics, or strategy statistics. Those fields remain `null`, and the
report status is `PARTIAL`.

Profit factor remains `null` until at least one losing closed trade exists.

Max drawdown remains `null` in Version 1 because a dated portfolio equity curve
has not yet been implemented. The report explicitly warns about this missing
evidence.

## Reconciliation

The engine verifies:

- closed-position realized P/L matches the Trade History Manager summary;
- portfolio value equals initial account capital plus realized and unrealized
  paper P/L;
- all source artifacts preserve paper-only safety values.

Conflicting evidence stops publication.

## Safety

Permanent values:

- `paper_trade_mode = true`
- `live_trading_enabled = false`
- `broker_execution_enabled = false`
- `order_placement_enabled = false`
- `capital_movement_enabled = false`
- `direct_database_writes = false`

## CLI

```bash
python run_performance_analytics.py \
  --ledger-dir results/paper_ledger \
  --output-dir results/paper_ledger
```

## Version 1 limitation

The engine evaluates existing evidence only. It does not implement exit rules,
persistent daily equity snapshots, drawdown calculations, or AI CIO display
mapping.

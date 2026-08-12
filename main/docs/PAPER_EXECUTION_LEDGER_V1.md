# Paper Execution Ledger Version 1

## Purpose

Convert existing positive portfolio allocation recommendations into persistent,
paper-only positions using completed daily CSV closing prices.

## Safety

- `paper_trade_mode=True`
- `live_trading_enabled=False`
- `broker_execution_enabled=False`
- `order_placement_enabled=False`
- `capital_movement_enabled=False`
- No Robinhood order, cancellation, transfer, or account mutation integration

## Inputs

- `results/portfolio_allocations.json`
- `data/<SYMBOL>.csv`
- `--account-capital`

Reserve rows such as `SGOV`, `CASH`, and `RESERVE` are not converted into
stock positions.

## Outputs

Written atomically under `results/paper_ledger/` by default:

- `open_positions.json`
- `trade_history.json`
- `paper_portfolio_summary.json`

## Version 1 behavior

- Creates one paper BUY for each newly positive stock allocation.
- Uses the latest completed daily `Close` as the simulated fill price.
- Calculates fractional shares, cost basis, cash balance, market value, and
  unrealized P/L.
- Preserves existing positions across runs.
- Does not duplicate BUY records on repeated runs.
- Fails before publication when required market data is missing or invalid.
- Does not implement sells. Exit execution is a separate governed milestone.

## Command

```bash
python run_paper_execution.py \
  --allocations results/portfolio_allocations.json \
  --data-dir data \
  --state-dir results/paper_ledger \
  --account-capital 4500
```

The account capital supplied here must be the strategy-specific `SWING-001`
paper allocation, not total Enterprise account capital.

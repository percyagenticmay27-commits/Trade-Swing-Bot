# Paper Portfolio Manager Version 1

## Purpose

The Paper Portfolio Manager marks the persistent Swing paper ledger to the latest completed local daily Close and publishes authoritative paper-portfolio evidence.

It does not fetch market data, place orders, access a broker, move capital, or write to the AI CIO database.

## Inputs

- `results/paper_ledger/open_positions.json`
- `data/<SYMBOL>.csv`
- Strategy-specific `SWING-001` account capital supplied by the caller

## Outputs

- `results/paper_ledger/paper_portfolio_summary.json`
- `results/paper_ledger/paper_portfolio_positions.json`

## Valuation

```text
positions_market_value = sum(shares × latest completed Close)
cash_balance = account_capital - invested_capital
portfolio_value = cash_balance + positions_market_value
unrealized_pnl = positions_market_value - invested_capital
portfolio_return_percent = unrealized_pnl / account_capital × 100
```

The authoritative valuation source is:

```text
PAPER_LEDGER_MARK_TO_MARKET
```

## Enterprise KPI integration

`enterprise_strategy_kpi_publisher.py` now prefers the paper portfolio summary over the prior allocation proxy. The paper ledger account capital must equal the preserved `SWING-001` allocation or publication fails safely.

When valid ledger evidence exists, the Enterprise KPI artifact includes:

- `portfolio_value`
- `portfolio_value_source = PAPER_LEDGER_MARK_TO_MARKET`
- `cash_balance`
- `invested_capital`
- `positions_market_value`
- `unrealized_pnl`
- `portfolio_return_percent`
- `position_count`

The existing Dividend-hosted AI CIO still controls how these fields are rendered on `jshouseapi.com`.

## Safety

Permanent locks:

- `paper_trade_mode = true`
- `live_trading_enabled = false`
- `broker_execution_enabled = false`
- `order_placement_enabled = false`
- `capital_movement_enabled = false`
- `direct_database_writes = false`

## Controlled server command

```bash
python run_paper_portfolio_manager.py \
  --ledger-dir results/paper_ledger \
  --data-dir data \
  --output-dir results/paper_ledger \
  --account-capital 4500
```

Then republish Enterprise KPI evidence:

```bash
python publish_enterprise_strategy_kpis.py \
  --strategy-allocations-file results/enterprise_strategy_allocations.json
```

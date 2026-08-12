# Trade History Manager Version 1

## Purpose

The Trade History Manager converts the append-only paper trade event ledger into validated lifecycle evidence. It remains paper-only and does not connect to Robinhood, place orders, move capital, or write to a database.

## Input

- `results/paper_ledger/trade_history.json`

The input must contain a `trades` list. Each event requires a unique `trade_id`, symbol, `BUY` or `SELL` side, ISO trade date, positive price and shares, matching notional, strategy name, reason, and `paper_trade_mode=true`.

## Outputs

- `results/paper_ledger/managed_trade_history.json`
- `results/paper_ledger/closed_positions.json`
- `results/paper_ledger/trade_history_summary.json`

All files are written atomically.

## Accounting

Version 1 uses FIFO matching. SELL events consume the oldest available BUY lots for the same symbol. Partial exits are supported. A SELL that exceeds available paper shares fails validation.

Closed trade evidence includes entry and exit dates, prices, shares, cost basis, proceeds, realized P/L, realized return percentage, holding days, strategy, and exit reason.

## Evidence rules

- Duplicate trade IDs are rejected.
- Non-paper events are rejected.
- Unsupported sides are rejected.
- Invalid dates, prices, shares, and notionals are rejected.
- A SELL before its matched BUY is rejected.
- Win rate is `null` until at least one non-breakeven closed trade exists.
- Missing closed trades create a warning, not fabricated performance.

## Safety locks

- `paper_trade_mode=true`
- `live_trading_enabled=false`
- `broker_execution_enabled=false`
- `order_placement_enabled=false`
- `capital_movement_enabled=false`
- `direct_database_writes=false`

## Local validation

```bash
python -m py_compile src/swing_trade_bot/trade_history_manager.py
python -m py_compile run_trade_history_manager.py
python -m pytest tests/test_trade_history_manager.py -v
```

## Controlled run

```bash
python run_trade_history_manager.py \
  --trade-history results/paper_ledger/trade_history.json \
  --output-dir results/paper_ledger
```

Version 1 does not decide when to sell. It processes validated SELL events after a governed exit component records them in the paper ledger.

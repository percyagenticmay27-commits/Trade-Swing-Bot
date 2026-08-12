# Swing Enterprise KPI Publisher Version 2

## Purpose

The publisher creates one read-only, AI-CIO-readable strategy evidence artifact from authoritative Swing outputs. It remains external to the AI CIO and does not import Dividend Bot production modules.

## Output

`results/enterprise_strategy_kpis.json`

## Required evidence

- `results/enterprise_strategy_allocations.json`
- The mapping must contain `strategy_allocations["SWING-001"]`.
- Total account capital is never accepted as a substitute for Swing capital.

## Optional authoritative evidence

- `results/paper_ledger/paper_portfolio_summary.json`
- `results/paper_ledger/paper_portfolio_positions.json`
- `results/paper_ledger/trade_history_summary.json`
- `results/paper_ledger/paper_performance.json`
- `results/opportunity_quality.json` or the recognized legacy filename
- `results/watchlist_report.json`
- `results/portfolio_allocations.json`
- `results/executive_dashboard.json`

Missing optional evidence creates explicit null fields and warnings. Values are not invented.

## Published groups

- Identity and allocation
- Mark-to-market portfolio value
- Cash, invested capital, and positions market value
- Open paper holdings
- Realized, unrealized, and total P/L
- Trade and closed-trade counts
- Win rate when closed-trade evidence exists
- Opportunity Quality when available
- Watchlist count when available
- Deterministic capabilities
- Artifact availability and warnings

## Safety

The following values are permanently locked:

- `paper_trade_mode = true`
- `paper_compatible = true`
- `advisory_only = true`
- `reporting_only = true`
- `live_trading_enabled = false`
- `broker_execution_enabled = false`
- `order_placement_enabled = false`
- `capital_movement_enabled = false`
- `automatic_activation_allowed = false`
- `direct_database_writes = false`

Unsafe source evidence is rejected before publication.

## Atomic publication

The publisher writes a temporary file, flushes and synchronizes it, and then atomically replaces the final JSON. The AI CIO reads only the completed final artifact.

## Run

```bash
python publish_enterprise_strategy_kpis.py \
  --strategy-allocations-file results/enterprise_strategy_allocations.json
```

The output declares `kpi_contract_version = "2.0"` and `schema_version = "2.0"`.

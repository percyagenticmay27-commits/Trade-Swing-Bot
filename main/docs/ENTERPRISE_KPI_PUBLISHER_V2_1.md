# Enterprise KPI Publisher Version 2.1

## Purpose

Enterprise KPI Publisher v2.1 packages the Swing Bot's existing paper-only evidence into one deterministic JSON artifact for the existing AI CIO host.

It does not modify strategy calculations, execute trades, move capital, import Dividend production modules, or update the AI CIO dashboard.

## Output

`results/enterprise_strategy_kpis.json`

## Evidence Sections

- `portfolio`
- `holdings`
- `performance_summary`
- `trade_history`
- `strategy_intelligence`
- `dashboard_sections`
- `artifact_contract`

## Source Evidence

The publisher uses existing Swing outputs only:

- `results/portfolio_allocations.json`
- `results/executive_dashboard.json`
- `results/opportunity_quality.json`
- `results/watchlist_report.json`
- `results/paper_ledger/paper_portfolio_summary.json`
- `results/paper_ledger/paper_portfolio_positions.json`
- `results/paper_ledger/managed_trade_history.json`
- `results/paper_ledger/trade_history_summary.json`
- `results/paper_ledger/closed_positions.json`
- `results/paper_ledger/paper_performance.json`

All runtime evidence is optional. Missing evidence is listed under `missing_optional_artifacts`; values are never fabricated.

## Safety

- `paper_trade_mode=true`
- `live_trading_enabled=false`
- `broker_execution_enabled=false`
- `order_placement_enabled=false`
- `capital_movement_enabled=false`
- `direct_database_writes=false`

## Validation

```bash
python -m py_compile src/swing_trade_bot/enterprise_strategy_kpi_publisher_v21.py
python -m py_compile publish_enterprise_strategy_kpis_v21.py
python -m pytest tests/test_enterprise_strategy_kpi_publisher_v21.py -v
```

## Publication

```bash
python publish_enterprise_strategy_kpis_v21.py \
  --strategy-allocations-file results/enterprise_strategy_allocations.json
```

This produces the evidence package. The Dividend-hosted AI CIO still owns ingestion and dashboard rendering; host-side mapping may be required for fields the existing dashboard does not already recognize.

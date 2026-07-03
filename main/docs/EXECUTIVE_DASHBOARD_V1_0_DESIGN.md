# Executive Dashboard Version 1.0 Design

## Purpose

The Executive Dashboard is the high-level control panel for the paper-only swing trading system. It summarizes the current state of the full system using existing outputs only.

## Required Inputs

- portfolio_allocations.json
- portfolio_manager_report.csv
- strategy_comparison.json
- strategy_recommendations.csv
- confidence_report.json
- watchlist_report.json

## Optional Inputs

- stock_performance_report.json
- weekly_stock_report.json
- earnings_report.json
- theme_momentum.json
- source_confluence.json
- opportunity_quality_report.json

## Public Dataclasses

- DashboardSummary
- ExecutiveDashboard

## Public Functions

- build_executive_dashboard
- write_executive_dashboard
- format_executive_dashboard_markdown

## JSON Schema

Top-level fields:

- paper_trade_mode
- summary
- risk_flags
- suggested_actions
- warnings
- source_files

## Markdown Layout

- Executive Dashboard title
- Paper-only statement
- Summary Metrics
- Risk Flags
- Suggested Actions
- Warnings

## Summary Metrics

- Allocated Percent
- SGOV Reserve Percent
- Active Positions
- Watchlist Count
- High Confidence Count
- Strategy B Count
- Warning Count

## Risk Flags

- Low SGOV reserve
- Position allocation cap breach
- Theme allocation cap breach
- Missing required output files

## Suggested Actions

Suggested actions are review-only and paper-only. They do not place orders.

## Testing Plan

- Confirm missing optional files create warnings, not failures
- Confirm missing required files create warnings and risk flags
- Confirm paper_trade_mode=False is rejected
- Confirm JSON and Markdown outputs are written
- Confirm summary metrics are computed from existing outputs only

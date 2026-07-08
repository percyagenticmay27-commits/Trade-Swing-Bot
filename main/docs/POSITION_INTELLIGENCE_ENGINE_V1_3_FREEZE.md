# Position Intelligence Engine Version 1.3 Freeze

## Purpose

The Position Intelligence Engine is the unified daily decision engine for each tracked symbol and active paper position in the Trade-Swing-Bot project.

It consolidates existing paper-only reports into one final review-oriented recommendation per symbol.

It answers:

> What should happen to this symbol or position today?

This module does not create new scores. It orchestrates existing Opportunity Quality, Strategy Assignment, Trade Lifecycle, Profit Protection, Re-entry, Exit Review, and Portfolio Allocation outputs.

## Frozen Module

- `src/swing_trade_bot/position_intelligence_engine.py`

## Frozen Test Suite

- `tests/test_position_intelligence_engine.py`

## Verified Test Results

Verified locally from the repository `main` folder:

- `python -m py_compile src\swing_trade_bot\position_intelligence_engine.py`: PASSED
- `python -m pytest tests\test_position_intelligence_engine.py -v`: 35 passed

No failed tests.

## Version 1.3 Boundary

The module is frozen as a Version 1.3 paper-only orchestration module.

It must not:

- connect to Robinhood
- connect to brokers
- place real orders
- place paper broker orders
- fetch live market data
- fetch live news
- modify allocations directly
- create new scores
- override Opportunity Quality
- override Entry Score
- override Strategy Assignment

## Permanent Architecture Rules

The Position Intelligence Engine follows these permanent rules:

- `paper_trade_mode=True` is mandatory.
- Existing reports are the source of truth.
- The module produces review-oriented recommendations only.
- The module does not generate new investment scores.
- The module does not modify allocations.
- The module does not execute trades.
- The module does not access broker APIs.
- Missing required inputs are errors.
- Missing optional inputs create warnings only.

## Required Inputs

- `results/opportunity_quality.json`
- `results/strategy_assignments.json`
- `results/trade_lifecycle_report.json`
- `results/profit_protection_report.json`
- `results/reentry_report.json`
- `results/exit_review_report.json`
- `results/portfolio_allocations.json`

## Optional Inputs

- `results/executive_dashboard.json`
- `results/confidence_report.json`
- `results/confidence_report.csv`
- `results/earnings_report.json`
- `results/earnings_report.csv`
- `results/position_lifecycle.json`
- `results/portfolio_risk.json`
- `results/entry_scores.json`
- `results/conviction_scores.json`
- `results/momentum_scores.json`
- `data/position_intelligence_context.json`
- `data/position_intelligence_context.csv`

## Outputs

- `results/position_intelligence.json`
- `results/position_intelligence.md`

## Supported Decision States

- `MONITOR_WATCHLIST`
- `REVIEW_ENTRY`
- `REVIEW_REENTRY`
- `HOLD_ACTIVE_POSITION`
- `REVIEW_PROFIT_PROTECTION`
- `REVIEW_EXIT`
- `WAIT_FOR_ENTRY`
- `WAIT_FOR_REENTRY`
- `REMOVE_FROM_ACTIVE_REVIEW`
- `NEEDS_MANUAL_REVIEW`
- `NO_ACTION_REQUIRED`

## Strategy A Handling

Strategy A remains thesis-preservation oriented.

The Position Intelligence Engine does not force Strategy A exits. It consolidates lifecycle, exit-review, and quality context into a review state.

## Strategy B Handling

Strategy B remains capital-preservation oriented.

If existing lifecycle or exit-review outputs indicate a Strategy B capital-preservation review, the Position Intelligence Engine escalates the symbol to `REVIEW_EXIT` and emits the appropriate review flags.

The module does not execute the exit. It only identifies the review state.

## Priority Order

Recommended priority order:

1. Exit Review
2. Profit Protection Review
3. Re-entry Review
4. Entry Review
5. Active Position Hold Review
6. Wait for Entry
7. Wait for Re-entry
8. Monitor Watchlist
9. Remove from Active Review
10. Manual Review
11. No Action Required

## Position Intelligence Workflow

The Position Intelligence Engine reads existing reports and builds one consolidated row per symbol.

For each symbol it summarizes:

- Strategy Assignment
- Opportunity Quality
- Entry Gate Status
- Lifecycle State
- Portfolio Allocation
- Profit Protection State
- Re-entry State
- Exit Review State
- Final Decision State
- Suggested Review Action

## Final Freeze Statement

`position_intelligence_engine.py` is frozen as the Version 1.3 Position Intelligence Engine.

Future modifications should be limited to verified bug fixes or future version enhancements.

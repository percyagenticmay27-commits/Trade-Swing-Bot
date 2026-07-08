# Position Intelligence Engine Version 1.3 Design

## 1. Purpose

The Position Intelligence Engine is the unified daily decision engine for each tracked symbol and active paper position.

It combines existing reports into one final review-oriented recommendation per symbol.

It answers:

> What should happen to this symbol or position today?

This module does not create new scores. It orchestrates existing intelligence, lifecycle, strategy, allocation, profit-protection, re-entry, and exit-review outputs.

The module is paper-only and review-oriented.

It must never:

- connect to Robinhood
- connect to brokers
- place real orders
- place paper broker orders
- fetch live market data
- fetch live news
- modify allocations directly
- generate buy, sell, order, execute, or trade-now instructions

## 2. Required Inputs

Required files:

- `results/opportunity_quality.json`
- `results/strategy_assignments.json`
- `results/trade_lifecycle_report.json`
- `results/profit_protection_report.json`
- `results/reentry_report.json`
- `results/exit_review_report.json`
- `results/portfolio_allocations.json`

Missing required inputs must raise clear errors.

## 3. Optional Inputs

Optional files:

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

Missing optional inputs should create warnings, not failures.

## 4. Outputs

The module writes:

- `results/position_intelligence.json`
- `results/position_intelligence.md`

## 5. Public Dataclasses

### PositionIntelligenceWarning

Fields:

- `source`
- `severity`
- `message`

### SymbolPositionIntelligence

Fields:

- `symbol`
- `decision_state`
- `strategy_assignment`
- `opportunity_quality_score`
- `opportunity_classification`
- `entry_gate_status`
- `lifecycle_state`
- `allocation_pct`
- `profit_protection_state`
- `reentry_state`
- `exit_review_state`
- `final_recommendation`
- `summary`
- `source`

### PositionIntelligenceRiskFlag

Fields:

- `flag_type`
- `symbol`
- `severity`
- `message`
- `source`

### PositionIntelligenceReviewAction

Fields:

- `action_type`
- `symbol`
- `priority`
- `message`
- `source`

### PositionIntelligenceSummaryMetrics

Fields:

- `paper_trade_mode`
- `symbols_analyzed`
- `monitor_watchlist_count`
- `review_entry_count`
- `review_reentry_count`
- `hold_active_position_count`
- `review_profit_protection_count`
- `review_exit_count`
- `wait_for_entry_count`
- `wait_for_reentry_count`
- `remove_from_active_review_count`
- `manual_review_count`
- `no_action_required_count`
- `strategy_a_count`
- `strategy_b_count`
- `risk_flag_count`
- `review_action_count`
- `warning_count`

### PositionIntelligenceReport

Fields:

- `report_version`
- `generated_by`
- `generated_at_utc`
- `paper_trade_mode`
- `data_sources`
- `summary_metrics`
- `symbol_position_intelligence`
- `risk_flags`
- `suggested_review_actions`
- `warnings`
- `sections`

## 6. Public Functions

Required locked-module pattern:

```python
build_position_intelligence_report(
    results_dir: str = "results",
    data_dir: str = "data"
) -> PositionIntelligenceReport
```

Builds and returns the report object only.

```python
write_position_intelligence_reports(
    output_dir: str,
    report: PositionIntelligenceReport
) -> None
```

Writes:

- `position_intelligence.json`
- `position_intelligence.md`

```python
build_and_write_position_intelligence_report(
    results_dir: str = "results",
    data_dir: str = "data"
) -> PositionIntelligenceReport
```

Convenience function that builds and writes reports.

Additional public helpers:

```python
format_position_intelligence_markdown(report: PositionIntelligenceReport) -> str
format_console_summary(report: PositionIntelligenceReport) -> str
```

Recommended internal helpers:

- `_load_required_json(...)`
- `_load_optional_json_or_csv(...)`
- `_build_data_source_status(...)`
- `_extract_symbols(...)`
- `_build_symbol_position_intelligence(...)`
- `_determine_decision_state(...)`
- `_determine_strategy_assignment(...)`
- `_extract_opportunity_quality(...)`
- `_extract_entry_gate(...)`
- `_extract_lifecycle_state(...)`
- `_extract_profit_protection_state(...)`
- `_extract_reentry_state(...)`
- `_extract_exit_review_state(...)`
- `_generate_position_intelligence_risk_flags(...)`
- `_generate_position_intelligence_review_actions(...)`
- `_priority_rank(...)`

## 7. JSON Schema

```json
{
  "report_version": "1.3",
  "generated_by": "position_intelligence_engine",
  "generated_at_utc": "ISO-8601 timestamp",
  "paper_trade_mode": true,
  "data_sources": {
    "required": {
      "opportunity_quality": "loaded",
      "strategy_assignments": "loaded",
      "trade_lifecycle_report": "loaded",
      "profit_protection_report": "loaded",
      "reentry_report": "loaded",
      "exit_review_report": "loaded",
      "portfolio_allocations": "loaded"
    },
    "optional": {
      "executive_dashboard": "loaded | missing",
      "confidence_report": "loaded | missing",
      "earnings_report": "loaded | missing",
      "position_lifecycle": "loaded | missing",
      "portfolio_risk": "loaded | missing",
      "entry_scores": "loaded | missing",
      "conviction_scores": "loaded | missing",
      "momentum_scores": "loaded | missing",
      "position_intelligence_context": "loaded | missing"
    }
  },
  "summary_metrics": {},
  "symbol_position_intelligence": [],
  "risk_flags": [],
  "suggested_review_actions": [],
  "warnings": [],
  "sections": {
    "position_intelligence_overview": {},
    "daily_decision_summary": {},
    "entry_reviews": {},
    "reentry_reviews": {},
    "active_positions": {},
    "profit_protection_reviews": {},
    "exit_reviews": {},
    "manual_reviews": {},
    "risk_summary": {},
    "review_plan": {}
  }
}
```

## 8. Markdown Layout

Required Markdown sections:

```text
# Position Intelligence Report

## Paper-Only Status
## Position Intelligence Overview
## Data Sources
## Summary Metrics
## Daily Decision Summary
## Symbol Position Intelligence
## Entry Reviews
## Re-entry Reviews
## Active Positions
## Profit Protection Reviews
## Exit Reviews
## Manual Reviews
## Risk Flags
## Suggested Review Actions
## Warnings
## Version 1.3 Scope
```

Markdown must clearly state:

- `paper_trade_mode=True`
- No Robinhood execution
- No broker integration
- No real orders placed
- No live market/news/price fetching
- Review actions only

## 9. Decision States

Allowed decision states:

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

## 10. Recommendation Logic

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

The engine should not create new scores. It should use existing reports and final statuses.

## 11. Strategy A vs Strategy B Handling

Strategy Assignment should be read from `strategy_assignments.json`.

Strategy A behavior:

- More thesis-preservation oriented
- Does not automatically escalate solely because of drawdown unless the lifecycle or exit review report indicates review is required
- Still remains paper-only and review-only

Strategy B behavior:

- Capital-preservation oriented
- A 10% loss review from lifecycle or exit-review reports should result in `REVIEW_EXIT`
- After exit, the symbol remains eligible for re-entry monitoring if Opportunity Quality remains high and Entry Gate becomes favorable

The engine must not execute either strategy. It only consolidates the recommended review state.

## 12. Profit Protection Handling

If `profit_protection_report.json` indicates review is required, the decision state should become:

- `REVIEW_PROFIT_PROTECTION`

This has higher priority than normal active holding but lower priority than exit review.

## 13. Exit Review Handling

If `exit_review_report.json` indicates review is required, or if lifecycle state is `EXIT_REVIEW`, decision state should become:

- `REVIEW_EXIT`

Exit review must remain advisory only.

## 14. Re-entry Handling

If `reentry_report.json` or Opportunity Quality final status indicates re-entry readiness, decision state should become:

- `REVIEW_REENTRY`

If Opportunity Quality remains high but Entry Gate is not favorable, decision state should become:

- `WAIT_FOR_REENTRY`

Re-entry requires:

- high Opportunity Quality
- Entry Gate favorable

Momentum alone is insufficient.

## 15. Opportunity Quality Handling

Opportunity Quality should be read from `opportunity_quality.json`.

The engine should use:

- `opportunity_quality_score`
- `opportunity_classification`
- `entry_gate_status`
- `lifecycle_state`
- `final_opportunity_status`

The engine should not recalculate Opportunity Quality.

## 16. Entry Gate Handling

Entry Gate is read from Opportunity Quality or `entry_scores.json` if needed.

Entry Gate controls timing.

The engine should not override Entry Gate logic.

## 17. Risk Flags

Allowed risk flag types:

- `exit_review_required`
- `profit_protection_review_required`
- `reentry_ready`
- `entry_ready`
- `high_quality_waiting_for_entry`
- `strategy_b_capital_preservation`
- `strategy_conflict`
- `missing_required_context`
- `missing_optional_context`
- `manual_review_required`

Severity values:

- `low`
- `medium`
- `high`
- `critical`

## 18. Suggested Review Actions

Allowed action types:

- `REVIEW_EXIT`
- `REVIEW_PROFIT_PROTECTION`
- `REVIEW_REENTRY`
- `REVIEW_ENTRY`
- `REVIEW_ACTIVE_POSITION`
- `MONITOR_WAIT_FOR_ENTRY`
- `MONITOR_WAIT_FOR_REENTRY`
- `MONITOR_WATCHLIST`
- `REVIEW_MANUAL_CONTEXT`
- `REMOVE_FROM_ACTIVE_REVIEW`
- `NO_ACTION_REQUIRED`

Actions should be sorted by priority:

- `critical`
- `high`
- `medium`
- `low`

Disallowed wording:

- buy
- sell
- order
- execute
- Robinhood
- broker
- trade now

Actions must say review, monitor, or verify context.

## 19. Testing Plan

Required tests for `tests/test_position_intelligence_engine.py`:

- `test_paper_trade_mode_enforced`
- `test_required_inputs_missing_raise_error`
- `test_optional_inputs_missing_create_warnings`
- `test_json_output_generation`
- `test_markdown_output_generation`
- `test_report_metadata`
- `test_data_source_status`
- `test_summary_metrics`
- `test_decision_states_are_allowed`
- `test_review_entry_state`
- `test_review_reentry_state`
- `test_hold_active_position_state`
- `test_review_profit_protection_state`
- `test_review_exit_state`
- `test_wait_for_entry_state`
- `test_wait_for_reentry_state`
- `test_monitor_watchlist_state`
- `test_strategy_a_handling`
- `test_strategy_b_capital_preservation_handling`
- `test_profit_protection_priority`
- `test_exit_review_priority`
- `test_reentry_requires_high_opportunity_quality`
- `test_reentry_requires_entry_favorable`
- `test_opportunity_quality_is_not_recalculated`
- `test_entry_gate_is_not_overridden`
- `test_risk_flags_generated`
- `test_suggested_review_actions_generated`
- `test_suggested_review_actions_sorted_by_priority`
- `test_no_robinhood_execution`
- `test_no_broker_execution`
- `test_no_order_fields`
- `test_no_buy_sell_execute_language`
- `test_no_live_market_news_price_fetching`
- `test_console_summary`
- `test_build_write_build_and_write_workflow`
- `test_malformed_required_json_raises_clear_error`
- `test_malformed_optional_json_creates_warning`
- `test_malformed_optional_csv_creates_warning`

Verification commands after implementation:

```bash
python -m py_compile src/swing_trade_bot/position_intelligence_engine.py
pytest tests/test_position_intelligence_engine.py -v
```

## 20. Version 1.3 Boundary

This module is an orchestration and daily decision-summary layer only.

It must not:

- create new scoring models
- place trades
- modify allocations
- fetch live data
- connect to brokers
- override Opportunity Quality
- override Entry Score
- override Strategy Assignment

## Final Design Statement

The Position Intelligence Engine consolidates the current paper-only state of each symbol into one daily review recommendation.

It is the bridge between scoring engines, lifecycle managers, and future capital deployment logic.

# Thesis Monitor Engine Version 1.3 Design

## 1. Purpose

The Thesis Monitor Engine answers one core question for each tracked leveraged swing opportunity:

> Would we still want this opportunity today based on the original thesis?

The module monitors whether the reason for tracking, entering, holding, or re-entering a symbol remains valid.

It is especially important for Strategy B capital preservation because a -10% paper exit does not automatically mean the underlying opportunity is bad. Thesis Monitor separates:

- temporary timing failure
- weakened thesis
- broken thesis

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
- `results/confidence_report.json` or `results/confidence_report.csv`
- `results/earnings_report.json` or `results/earnings_report.csv`

Missing required inputs must raise clear errors.

## 3. Optional Inputs

Optional files:

- `results/market_intelligence.json`
- `results/conviction_scores.json`
- `results/momentum_scores.json`
- `results/portfolio_risk.json`
- `results/position_intelligence.json`
- `results/trade_lifecycle_report.json`
- `results/profit_protection_report.json`
- `results/reentry_report.json`
- `results/exit_review_report.json`
- `results/stock_performance_report.json`
- `results/weekly_stock_report.json`
- `data/thesis_monitor_context.json`
- `data/thesis_monitor_context.csv`

Missing optional inputs should create warnings, not failures.

## 4. Outputs

The module writes:

- `results/thesis_monitor_report.json`
- `results/thesis_monitor_report.md`

## 5. Public Dataclasses

### ThesisMonitorWarning

Fields:

- `source`
- `severity`
- `message`

### SymbolThesisReview

Fields:

- `symbol`
- `thesis_state`
- `strategy_assignment`
- `opportunity_quality_score`
- `opportunity_classification`
- `confidence_state`
- `earnings_state`
- `market_intelligence_state`
- `conviction_state`
- `lifecycle_state`
- `thesis_summary`
- `review_reason`
- `source`

### ThesisMonitorRiskFlag

Fields:

- `flag_type`
- `symbol`
- `severity`
- `message`
- `source`

### ThesisMonitorReviewAction

Fields:

- `action_type`
- `symbol`
- `priority`
- `message`
- `source`

### ThesisMonitorSummaryMetrics

Fields:

- `paper_trade_mode`
- `symbols_analyzed`
- `thesis_strong_count`
- `thesis_intact_count`
- `thesis_weakening_count`
- `thesis_broken_count`
- `thesis_unknown_count`
- `strategy_a_count`
- `strategy_b_count`
- `risk_flag_count`
- `review_action_count`
- `warning_count`

### ThesisMonitorReport

Fields:

- `report_version`
- `generated_by`
- `generated_at_utc`
- `paper_trade_mode`
- `data_sources`
- `summary_metrics`
- `reviews`
- `risk_flags`
- `suggested_review_actions`
- `warnings`
- `sections`

## 6. Public Functions

Required locked-module pattern:

```python
build_thesis_monitor_report(results_dir: str = "results", data_dir: str = "data") -> ThesisMonitorReport
write_thesis_monitor_reports(output_dir: str, report: ThesisMonitorReport) -> None
build_and_write_thesis_monitor_report(results_dir: str = "results", data_dir: str = "data") -> ThesisMonitorReport
```

Additional public helpers:

```python
format_thesis_monitor_markdown(report: ThesisMonitorReport) -> str
format_console_summary(report: ThesisMonitorReport) -> str
```

## 7. JSON Schema

```json
{
  "report_version": "1.3",
  "generated_by": "thesis_monitor_engine",
  "generated_at_utc": "ISO-8601 timestamp",
  "paper_trade_mode": true,
  "data_sources": {
    "required": {
      "opportunity_quality": "loaded",
      "strategy_assignments": "loaded",
      "confidence_report": "loaded",
      "earnings_report": "loaded"
    },
    "optional": {
      "market_intelligence": "loaded | missing",
      "conviction_scores": "loaded | missing",
      "momentum_scores": "loaded | missing",
      "portfolio_risk": "loaded | missing",
      "position_intelligence": "loaded | missing",
      "trade_lifecycle_report": "loaded | missing",
      "profit_protection_report": "loaded | missing",
      "reentry_report": "loaded | missing",
      "exit_review_report": "loaded | missing",
      "stock_performance_report": "loaded | missing",
      "weekly_stock_report": "loaded | missing",
      "thesis_monitor_context": "loaded | missing"
    }
  },
  "summary_metrics": {},
  "reviews": [],
  "risk_flags": [],
  "suggested_review_actions": [],
  "warnings": [],
  "sections": {
    "thesis_overview": {},
    "strong_theses": {},
    "intact_theses": {},
    "weakening_theses": {},
    "broken_theses": {},
    "unknown_theses": {},
    "risk_summary": {},
    "review_plan": {}
  }
}
```

## 8. Markdown Layout

Required Markdown sections:

```text
# Thesis Monitor Report

## Paper-Only Status
## Thesis Overview
## Data Sources
## Summary Metrics
## Symbol Thesis Reviews
## Strong Theses
## Intact Theses
## Weakening Theses
## Broken Theses
## Unknown Theses
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

## 9. Thesis States

Allowed thesis states:

- `THESIS_STRONG`
- `THESIS_INTACT`
- `THESIS_WEAKENING`
- `THESIS_BROKEN`
- `THESIS_UNKNOWN`

## 10. Thesis State Logic

The Thesis Monitor must not create a new trading score.

It classifies thesis state using existing evidence only.

### THESIS_STRONG

Conditions may include:

- Opportunity Quality remains high or elite
- Confidence is high
- Earnings context is positive or not concerning
- Market Intelligence is positive
- Conviction remains strong

### THESIS_INTACT

Conditions may include:

- Opportunity Quality remains moderate or high
- Confidence is medium or high
- No major negative earnings or thesis warnings
- No broken-thesis signals

### THESIS_WEAKENING

Conditions may include:

- Opportunity Quality has fallen materially
- Confidence has deteriorated
- Earnings warning is present
- Market Intelligence has turned negative
- Conviction has weakened
- Position Intelligence has raised manual or exit review concerns

### THESIS_BROKEN

Conditions may include:

- Opportunity Quality is avoid/low with negative earnings or negative intelligence
- Confidence is low with negative thesis evidence
- Exit Review indicates thesis failure
- Manual thesis context marks the thesis as broken

### THESIS_UNKNOWN

Conditions may include:

- Required symbol-level context is insufficient
- Inputs are present but do not provide enough evidence for classification

## 11. Strategy A vs Strategy B Handling

Strategy A is thesis-preservation oriented.

A weakening or broken thesis is especially important for Strategy A because the strategy relies more heavily on the underlying investment case.

Strategy B is capital-preservation oriented.

A Strategy B -10% exit does not automatically mean the thesis is broken. Thesis Monitor should allow:

- `THESIS_STRONG` or `THESIS_INTACT` after a Strategy B exit
- re-entry monitoring if Opportunity Quality remains strong and Entry Gate later becomes favorable
- `THESIS_WEAKENING` or `THESIS_BROKEN` if the underlying reason for tracking the stock has deteriorated

## 12. Risk Flags

Allowed risk flag types:

- `thesis_weakening`
- `thesis_broken`
- `strategy_a_thesis_risk`
- `strategy_b_reentry_thesis_risk`
- `earnings_thesis_risk`
- `negative_market_intelligence`
- `low_confidence_thesis`
- `missing_required_context`
- `missing_optional_context`
- `manual_review_required`

Severity values:

- `low`
- `medium`
- `high`
- `critical`

## 13. Suggested Review Actions

Allowed action types:

- `REVIEW_STRONG_THESIS`
- `REVIEW_INTACT_THESIS`
- `REVIEW_WEAKENING_THESIS`
- `REVIEW_BROKEN_THESIS`
- `REVIEW_EARNINGS_THESIS_RISK`
- `REVIEW_MARKET_INTELLIGENCE_THESIS_RISK`
- `REVIEW_STRATEGY_A_THESIS_RISK`
- `REVIEW_STRATEGY_B_REENTRY_THESIS_RISK`
- `REVIEW_MANUAL_CONTEXT`
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

## 14. Testing Plan

Required tests for `tests/test_thesis_monitor_engine.py`:

- `test_paper_trade_mode_enforced`
- `test_required_inputs_missing_raise_error`
- `test_required_json_or_csv_supported`
- `test_optional_inputs_missing_create_warnings`
- `test_json_output_generation`
- `test_markdown_output_generation`
- `test_report_metadata`
- `test_data_source_status`
- `test_summary_metrics`
- `test_thesis_states_are_allowed`
- `test_thesis_strong_state`
- `test_thesis_intact_state`
- `test_thesis_weakening_state`
- `test_thesis_broken_state`
- `test_thesis_unknown_state`
- `test_strategy_a_thesis_risk_handling`
- `test_strategy_b_exit_does_not_automatically_break_thesis`
- `test_strategy_b_reentry_thesis_risk_handling`
- `test_opportunity_quality_is_not_recalculated`
- `test_confidence_handling`
- `test_earnings_risk_handling`
- `test_market_intelligence_handling`
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
- `test_malformed_required_csv_raises_clear_error`
- `test_malformed_optional_json_creates_warning`
- `test_malformed_optional_csv_creates_warning`

Verification commands after implementation:

```bash
python -m py_compile src/swing_trade_bot/thesis_monitor_engine.py
pytest tests/test_thesis_monitor_engine.py -v
```

## 15. Version 1.3 Boundary

This module is a thesis-validation and review layer only.

It must not:

- create trading scores
- place trades
- modify allocations
- fetch live data
- connect to brokers
- override Opportunity Quality
- override Entry Score
- override Position Intelligence
- override Strategy Assignment

## Final Design Statement

The Thesis Monitor Engine determines whether the original reason for tracking, holding, or re-entering a symbol remains valid.

It completes the Position Intelligence layer by separating temporary price/timing failure from true thesis deterioration.

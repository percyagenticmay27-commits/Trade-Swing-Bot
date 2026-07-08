# Thesis Monitor Engine Version 1.3 Design

## 1. Purpose

The Thesis Monitor Engine continuously evaluates whether the original investment thesis for each tracked symbol remains valid.

It answers:

> Would we still want to own or buy this company today?

This module evaluates thesis health independently from Entry Score.

Opportunity Quality determines whether a company is attractive.

Entry Score determines whether now is a favorable entry or re-entry window.

The Thesis Monitor determines whether the underlying reasons for owning or tracking the company still exist.

The module is paper-only, review-oriented, and uses existing project reports only.

## 2. Paper Trading Rules

The Thesis Monitor Engine must enforce:

- `paper_trade_mode=True`
- No Robinhood connection
- No broker APIs
- No order placement
- No buy/sell execution
- No live market/news/price fetching
- Review-oriented recommendations only
- No automatic allocation modification
- No new trading execution behavior

## 3. Required Inputs

Required files:

- `results/opportunity_quality.json`
- `results/market_intelligence.json`
- `results/conviction_scores.json`
- `results/momentum_scores.json`
- `results/market_regime.json`
- `results/strategy_assignments.json`
- `results/position_intelligence.json`
- `results/portfolio_allocations.json`

Missing required inputs must raise clear errors.

## 4. Optional Inputs

Optional files:

- `results/earnings_report.json`
- `results/earnings_report.csv`
- `results/confidence_report.json`
- `results/confidence_report.csv`
- `results/executive_dashboard.json`
- `results/weekly_stock_report.json`
- `results/source_confluence.json`
- `results/theme_momentum.json`
- `data/thesis_monitor_context.json`
- `data/thesis_monitor_context.csv`

Missing optional inputs should create warnings, not failures.

## 5. Output Files

The module writes:

- `results/thesis_monitor.json`
- `results/thesis_monitor.md`

## 6. Thesis States

Supported thesis states:

- `THESIS_STRENGTHENING`
- `THESIS_INTACT`
- `THESIS_WEAKENING`
- `THESIS_BROKEN`
- `MANUAL_REVIEW_REQUIRED`

## 7. Evaluation Factors

The engine should evaluate existing evidence for each symbol, including:

- Opportunity Quality trend or current quality state
- Fundamental quality when available through Opportunity Quality or context
- Market Intelligence trend or narrative direction
- Conviction trend or current conviction state
- Momentum trend or current momentum state
- Market Regime support
- Strategy Assignment
- Portfolio allocation status
- Position Intelligence state
- Earnings risk
- Source Confluence support
- Theme Momentum support
- Optional manual thesis context

The module must not create a new standalone investment score. It should classify thesis condition using existing report outputs and clearly explain the reason.

## 8. Public Dataclasses

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
- `market_intelligence_state`
- `conviction_state`
- `momentum_state`
- `market_regime_state`
- `position_intelligence_state`
- `allocation_pct`
- `earnings_risk_state`
- `primary_reason`
- `supporting_evidence`
- `risk_evidence`
- `suggested_review_action`
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
- `thesis_strengthening_count`
- `thesis_intact_count`
- `thesis_weakening_count`
- `thesis_broken_count`
- `manual_review_required_count`
- `strategy_a_count`
- `strategy_b_count`
- `allocated_symbol_count`
- `unallocated_symbol_count`
- `earnings_risk_count`
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
- `symbol_thesis_reviews`
- `risk_flags`
- `suggested_review_actions`
- `warnings`
- `sections`

## 9. Public Functions

Required locked-module pattern:

```python
build_thesis_monitor(
    results_dir: str = "results",
    data_dir: str = "data"
) -> ThesisMonitorReport
```

Builds and returns the Thesis Monitor report only.

```python
write_thesis_monitor(
    output_dir: str,
    report: ThesisMonitorReport
) -> None
```

Writes:

- `thesis_monitor.json`
- `thesis_monitor.md`

```python
build_and_write_thesis_monitor(
    results_dir: str = "results",
    data_dir: str = "data"
) -> ThesisMonitorReport
```

Convenience function that builds and writes reports.

Additional public helpers:

```python
format_thesis_monitor_markdown(report: ThesisMonitorReport) -> str
format_console_summary(report: ThesisMonitorReport) -> str
```

Recommended internal helpers:

- `_load_required_json(...)`
- `_load_optional_json_or_csv(...)`
- `_build_data_source_status(...)`
- `_extract_symbols(...)`
- `_build_symbol_thesis_review(...)`
- `_determine_thesis_state(...)`
- `_extract_opportunity_quality(...)`
- `_extract_market_intelligence_state(...)`
- `_extract_conviction_state(...)`
- `_extract_momentum_state(...)`
- `_extract_market_regime_state(...)`
- `_extract_position_intelligence_state(...)`
- `_extract_earnings_risk_state(...)`
- `_generate_thesis_risk_flags(...)`
- `_generate_thesis_review_actions(...)`
- `_priority_rank(...)`

## 10. JSON Schema

```json
{
  "report_version": "1.3",
  "generated_by": "thesis_monitor_engine",
  "generated_at_utc": "ISO-8601 timestamp",
  "paper_trade_mode": true,
  "data_sources": {
    "required": {
      "opportunity_quality": "loaded",
      "market_intelligence": "loaded",
      "conviction_scores": "loaded",
      "momentum_scores": "loaded",
      "market_regime": "loaded",
      "strategy_assignments": "loaded",
      "position_intelligence": "loaded",
      "portfolio_allocations": "loaded"
    },
    "optional": {
      "earnings_report": "loaded | missing",
      "confidence_report": "loaded | missing",
      "executive_dashboard": "loaded | missing",
      "weekly_stock_report": "loaded | missing",
      "source_confluence": "loaded | missing",
      "theme_momentum": "loaded | missing",
      "thesis_monitor_context": "loaded | missing"
    }
  },
  "summary_metrics": {},
  "symbol_thesis_reviews": [],
  "risk_flags": [],
  "suggested_review_actions": [],
  "warnings": [],
  "sections": {
    "thesis_summary": {},
    "thesis_state_by_symbol": {},
    "strengthening_thesis": {},
    "intact_thesis": {},
    "weakening_thesis": {},
    "broken_thesis": {},
    "manual_reviews": {},
    "risk_summary": {},
    "review_plan": {}
  }
}
```

## 11. Markdown Layout

Required Markdown sections:

```text
# Thesis Monitor Report

## Paper-Only Status
## Thesis Summary
## Data Sources
## Summary Metrics
## Thesis State by Symbol
## Strengthening Thesis
## Intact Thesis
## Weakening Thesis
## Broken Thesis
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

## 12. Thesis State Logic

The engine should classify thesis state using existing evidence.

Recommended logic:

### THESIS_STRENGTHENING

Use when most evidence is supportive:

- Opportunity Quality is high or elite
- Market Intelligence is positive
- Conviction is high
- Momentum is supportive
- Market Regime is supportive or neutral
- No major earnings risk
- Position Intelligence does not indicate exit review

### THESIS_INTACT

Use when evidence remains acceptable:

- Opportunity Quality is moderate to high
- Market Intelligence is not meaningfully negative
- Conviction is not weak
- Momentum is neutral or supportive
- No broken-thesis evidence appears

### THESIS_WEAKENING

Use when evidence has deteriorated but is not fully broken:

- Opportunity Quality has fallen
- Market Intelligence has turned negative or mixed
- Conviction has weakened
- Momentum is weak
- Earnings risk is elevated
- Position Intelligence indicates manual review or wait state

### THESIS_BROKEN

Use when core ownership reasons are no longer supported:

- Opportunity Quality is low or avoid
- Market Intelligence is strongly negative
- Conviction is weak
- Earnings risk is severe
- Position Intelligence indicates exit review
- Existing evidence indicates the thesis no longer supports ongoing review

### MANUAL_REVIEW_REQUIRED

Use when required evidence exists but is conflicting, malformed in meaning, or insufficient to classify reliably.

## 13. Strategy A Handling

Strategy A emphasizes thesis preservation.

If Strategy A symbols move to `THESIS_WEAKENING` or `THESIS_BROKEN`, the module should emit higher-priority review actions because the thesis is central to Strategy A behavior.

## 14. Strategy B Handling

Strategy B emphasizes capital preservation.

A Strategy B 10% loss review does not automatically mean the thesis is broken.

The Thesis Monitor must distinguish between:

- timing failure / capital-preservation exit
- broken underlying thesis

A Strategy B symbol may be exited for capital preservation while still remaining `THESIS_INTACT` or `THESIS_STRENGTHENING` if Opportunity Quality and supporting evidence remain strong.

## 15. Entry Score Independence

Entry Score is not part of thesis validity.

A blocked entry does not mean the thesis is broken.

Entry Score answers:

> Is now an appropriate time to enter or re-enter?

Thesis Monitor answers:

> Are the original reasons for ownership or tracking still valid?

## 16. Risk Flags

Allowed risk flag types:

- `thesis_weakening`
- `thesis_broken`
- `strategy_a_thesis_risk`
- `strategy_b_exit_but_thesis_intact`
- `earnings_thesis_risk`
- `negative_market_intelligence`
- `conviction_deterioration`
- `momentum_deterioration`
- `market_regime_pressure`
- `manual_review_required`
- `missing_optional_context`

Severity values:

- `low`
- `medium`
- `high`
- `critical`

## 17. Suggested Review Actions

Allowed action types:

- `REVIEW_STRENGTHENING_THESIS`
- `REVIEW_INTACT_THESIS`
- `REVIEW_WEAKENING_THESIS`
- `REVIEW_BROKEN_THESIS`
- `REVIEW_STRATEGY_A_THESIS_RISK`
- `REVIEW_STRATEGY_B_REENTRY_THESIS`
- `REVIEW_EARNINGS_THESIS_RISK`
- `REVIEW_MANUAL_CONTEXT`
- `MONITOR_THESIS`
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

Actions must use review, monitor, verify, or reassess language.

## 18. SYSTEM_MODE Behavior

`SYSTEM_MODE` controls presentation only.

QA Mode should display:

- full thesis reasoning
- all evidence fields
- risk evidence
- supporting evidence
- optional context warnings

LIVE Mode should display:

- symbol
- thesis state
- primary reason
- highest-priority risk flag
- suggested review action

Calculations must be identical in QA and LIVE modes.

## 19. Permanent Architecture Rules

The Thesis Monitor Engine follows these rules:

- Paper-only
- Review-only
- No execution
- Uses existing reports only
- No new scoring system
- Missing required inputs = error
- Missing optional inputs = warning
- SYSTEM_MODE controls presentation only
- Entry Score does not determine thesis validity
- Strategy B loss exit does not automatically mean thesis broken

## 20. Testing Plan

Required tests for `tests/test_thesis_monitor_engine.py`:

- `test_paper_trade_mode_enforced`
- `test_required_inputs_missing_raise_error`
- `test_optional_inputs_missing_create_warnings`
- `test_json_output_generation`
- `test_markdown_output_generation`
- `test_report_metadata`
- `test_data_source_status`
- `test_summary_metrics`
- `test_allowed_thesis_states`
- `test_thesis_strengthening_state`
- `test_thesis_intact_state`
- `test_thesis_weakening_state`
- `test_thesis_broken_state`
- `test_manual_review_required_state`
- `test_strategy_a_thesis_risk_handling`
- `test_strategy_b_exit_does_not_automatically_break_thesis`
- `test_entry_score_does_not_determine_thesis_validity`
- `test_negative_market_intelligence_creates_risk_flag`
- `test_conviction_deterioration_creates_risk_flag`
- `test_momentum_deterioration_creates_risk_flag`
- `test_earnings_risk_creates_risk_flag`
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
- `test_system_mode_presentation_only`

Verification commands after implementation:

```bash
python -m py_compile src/swing_trade_bot/thesis_monitor_engine.py
python -m pytest tests/test_thesis_monitor_engine.py -v
```

## 21. Version 1.3 Boundary

This module is a thesis-health classification and review layer only.

It must not:

- create new scores
- place trades
- modify allocations
- fetch live data
- connect to brokers
- override Opportunity Quality
- override Entry Score
- override Strategy Assignment
- override Position Intelligence

## Final Design Statement

The Thesis Monitor Engine validates whether the original reasons for owning or tracking a symbol remain intact.

It completes the investment-thesis layer before capital deployment and paper-trade execution planning.

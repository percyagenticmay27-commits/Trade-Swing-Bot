# Exit Review Manager v1.3 Design

## Purpose

The Exit Review Manager is a paper-only research component. It determines whether a simulated position requires a deeper exit review based on strategy policy, thesis status, opportunity quality, drawdown, profit giveback, and market conditions.

It does not place real orders, does not connect to Robinhood, and does not connect to any broker.

## Review Outcomes

- continue_holding
- monitor_closely
- review_required
- high_priority_review
- thesis_broken_review
- strategy_b_reentry_review

## Strategy A Behavior

Strategy A is thesis-based. A drawdown alone is not enough to escalate unless quality, thesis, market regime, or other evidence has weakened.

Strategy A may still escalate if thesis evidence is broken or opportunity quality has materially declined.

## Strategy B Behavior

Strategy B is capital-protection oriented. When the configured paper drawdown threshold is reached, the position should move into reentry review research even if the thesis remains intact.

## Inputs

- symbol
- active strategy assignment
- lifecycle state
- opportunity quality score
- opportunity quality trend
- market regime score
- thesis intact flag
- unrealized percent
- drawdown from high percent
- profit protection zone
- reentry state

## Outputs

- results/exit_review_report.json
- results/exit_review_report.md

## Permanent Rules

- paper_trade_mode=True is mandatory
- no real order placement
- no Robinhood execution
- no brokerage API execution
- outputs are research reports only

# Profit Protection Manager v1.3 Design

## Purpose

The Profit Protection Manager is a paper-only research component. It classifies simulated unrealized gain levels and drawdown-from-high levels so the system can explain when a paper position has entered a protection review zone.

It does not place real orders, does not connect to Robinhood, and does not connect to any broker.

## Review Zones

- no_position_data
- below_protection_zone
- standard_protection_zone
- strong_trend_zone
- giveback_review_zone

## Default Paper Thresholds

- 20% unrealized gain: standard protection review zone
- 30% unrealized gain: strong trend review zone
- 5% drawdown from high after 20% gain: giveback review zone
- 10% drawdown from high after 30% gain: strong-trend giveback review zone

## Strategy Context

Strategy A uses thesis-based management. The protection result is evidence for review, not an automatic rule.

Strategy B uses mechanical paper rules. The protection result can be used by downstream modules to compare mechanical lifecycle behavior.

## Outputs

- results/profit_protection_report.json
- results/profit_protection_report.md

## Permanent Rules

- paper_trade_mode=True is mandatory
- no real order placement
- no Robinhood execution
- no brokerage API execution
- outputs are research reports only

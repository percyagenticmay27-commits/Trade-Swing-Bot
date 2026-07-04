# Strategy Assignment Engine v1.3 Design

## Purpose

The Strategy Assignment Engine is a paper-only research component. It assigns Strategy A or Strategy B to each ticker using rolling simulated performance evidence.

It does not place real orders, does not connect to any broker, and does not deploy capital.

## Strategies

- Strategy A: thesis-based management. A short-term pullback alone is not enough evidence to change the ticker policy.
- Strategy B: mechanical risk-management research policy. It compares whether a rule-based approach performs better for that ticker in paper results.

## Review Windows

- 1 week: early warning only
- 4 weeks: minimum valid review
- 8 weeks: preferred decision window
- 12 weeks / 3 months: high-confidence decision window

## Cooldown Rule

After a ticker changes assigned strategy, it must remain on that strategy for at least 4 weeks before another change can be considered.

## Switch Criteria

A ticker may change strategy only when the challenger clears all configured evidence rules:

- better total return by the configured margin
- acceptable maximum drawdown difference
- enough observations for the selected review window
- profit factor not worse when that rule is enabled
- no active cooldown period

## Outputs

- results/strategy_assignments.csv
- results/strategy_assignments.json
- results/strategy_assignments.md

## Permanent Rules

- paper_trade_mode=True is mandatory
- no real order placement
- no Robinhood execution
- no brokerage API execution
- outputs are research reports only

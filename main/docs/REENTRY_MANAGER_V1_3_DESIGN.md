# Reentry Manager v1.3 Design

## Purpose

The Reentry Manager is a paper-only research component. It evaluates whether a ticker that has moved into reentry watch has enough simulated evidence to become reentry-ready again.

It does not place real orders, does not connect to Robinhood, and does not connect to any broker.

## Reentry States

- no_reentry_context
- reentry_watch
- reentry_not_ready
- reentry_setup_improving
- reentry_ready
- reentry_blocked

## Inputs

Required inputs:

- symbol
- active strategy assignment
- prior lifecycle state
- opportunity quality score
- entry score
- market regime score
- thesis intact flag
- distance from preferred reentry level when available

Optional inputs:

- days since prior paper exit/review
- notes

## Default Evidence Rules

A ticker can become reentry-ready when:

- thesis is intact
- opportunity quality score is above threshold
- entry score is above threshold
- market regime score is above threshold
- price is within the configured distance from the preferred reentry level
- minimum wait period has passed

## Strategy Context

Strategy A uses thesis-based evidence. Reentry readiness depends heavily on whether the thesis remains intact.

Strategy B uses mechanical paper research. Reentry readiness also requires the configured wait period and reentry level proximity.

## Outputs

- results/reentry_report.json
- results/reentry_report.md

## Permanent Rules

- paper_trade_mode=True is mandatory
- no real order placement
- no Robinhood execution
- no brokerage API execution
- outputs are research reports only

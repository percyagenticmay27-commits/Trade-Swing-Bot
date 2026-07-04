# Trade Lifecycle Manager v1.3 Design

## Purpose

The Trade Lifecycle Manager is a paper-only research component. It tracks the simulated lifecycle state of each ticker and explains which paper-review stage the ticker is in.

It does not place real orders, does not connect to Robinhood, and does not connect to any broker.

## Lifecycle States

- candidate
- watchlist
- entry_ready
- paper_position
- profit_protection
- review_required
- reentry_watch
- closed_research

## Inputs

Required inputs:

- symbol
- active strategy assignment
- current lifecycle state
- entry price when available
- current price when available
- highest close since paper entry when available
- opportunity quality score
- entry score
- market regime score
- thesis intact flag

Optional inputs:

- notes
- days in lifecycle state
- last policy review date

## Strategy A Behavior

Strategy A is thesis-based. A short-term pullback alone is not enough evidence to move the ticker into review-required status.

The module checks whether the thesis remains intact using paper-only evidence such as quality score, market regime score, and notes.

## Strategy B Behavior

Strategy B is mechanical research policy. It uses configured paper thresholds to determine when a ticker should be reviewed for reentry research.

## Outputs

- results/trade_lifecycle_report.json
- results/trade_lifecycle_report.md

## Permanent Rules

- paper_trade_mode=True is mandatory
- no real order placement
- no Robinhood execution
- no brokerage API execution
- outputs are research reports only

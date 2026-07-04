# Thesis Monitor v1.4 Design

## Purpose

The Thesis Monitor is a paper-only research component. It evaluates whether the original reason for tracking or holding a ticker remains intact.

It does not place real orders, does not connect to Robinhood, and does not connect to any broker.

## Core Question

Is the original thesis still valid?

The module should not rely on price movement alone. It evaluates evidence across fundamentals, earnings, news, conviction, sector strength, market regime, technical deterioration, and opportunity quality trend.

## Thesis States

- strong
- intact
- weakening
- broken
- unknown

## Inputs

Required inputs:

- symbol
- active strategy assignment
- original thesis summary
- opportunity quality score
- opportunity quality trend
- fundamental score
- earnings score
- news sentiment score
- conviction score
- sector strength score
- market regime score
- technical health score

Optional inputs:

- notes
- last reviewed date
- analyst revision score
- institutional flow score

## Strategy Context

### Strategy A

Strategy A is thesis-based. Thesis Monitor output is a primary input. A drawdown alone should not break the thesis if underlying evidence remains strong.

### Strategy B

Strategy B is capital-protection based. Thesis Monitor output does not override the configured capital-protection rule, but it helps determine whether a ticker should remain on reentry watch after a paper exit.

## Outputs

- results/thesis_monitor_report.json
- results/thesis_monitor_report.md

## Permanent Rules

- paper_trade_mode=True is mandatory
- no real order placement
- no Robinhood execution
- no brokerage API execution
- outputs are research reports only

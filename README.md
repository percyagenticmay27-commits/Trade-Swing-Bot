# Trade-Swing-Bot

Paper-only swing trading research system.

This repository does not place real trades.
This repository does not connect to Robinhood for execution.
All strategy outputs are simulations, reports, CSV, JSON, and Markdown only.

paper_trade_mode=True is mandatory.

## Current Milestone

Version 1.3 foundation work adds a paper-only Strategy Assignment research module.

The module compares Strategy A and Strategy B by ticker using rolling simulated performance windows:

- 1 week: early warning only
- 4 weeks: minimum valid review
- 8 weeks: preferred decision window
- 12 weeks / 3 months: high-confidence decision window

A 4-week cooldown prevents rapid reassignment after a ticker policy changes.

Outputs are research reports only:

- results/strategy_assignments.csv
- results/strategy_assignments.json
- results/strategy_assignments.md

# Version 1.3 Release

## Release Purpose

Version 1.3 establishes the Position Intelligence Layer for the paper-only swing research system.

This release is research-only. It does not place real orders, does not connect to Robinhood, and does not connect to any broker.

## Completed Modules

### Strategy Assignment Engine

Path: `src/swing_trade_bot/strategy_assignment_engine.py`

Assigns Strategy A or Strategy B by ticker using rolling paper performance evidence.

### Trade Lifecycle Manager

Path: `src/swing_trade_bot/trade_lifecycle_manager.py`

Classifies lifecycle status for each paper position.

### Profit Protection Manager

Path: `src/swing_trade_bot/profit_protection_manager.py`

Classifies paper profit protection and giveback review zones.

### Reentry Manager

Path: `src/swing_trade_bot/reentry_manager.py`

Evaluates whether a ticker in reentry watch has enough evidence to become reentry-ready.

### Exit Review Manager

Path: `src/swing_trade_bot/exit_review_manager.py`

Classifies whether a paper position requires deeper review.

### Executive Dashboard Integration

Path: `src/swing_trade_bot/executive_dashboard.py`

Adds awareness of Version 1.3 Position Intelligence outputs.

## Strategy A Rule

Strategy A is thesis-based. A drawdown alone is not enough to escalate unless thesis, quality, market regime, or other evidence weakens.

## Strategy B Rule

Strategy B is capital-protection based. The default configured paper drawdown threshold is 10%. When reached, the ticker enters reentry review research.

## Validation Commands

Run from the repository root:

```bash
python -m pip install -e ./main
python -m unittest discover -s main/tests -v
```

GitHub Actions workflow added:

```text
.github/workflows/tests.yml
```

## Release Status

Version 1.3 is frozen for QA.

Future planned work:

- Thesis Monitor
- Capital Reallocation Engine
- Strategy Performance Analytics
- Version 2.0 intelligence layer

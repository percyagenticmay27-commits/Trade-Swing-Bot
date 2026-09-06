# Forward Primary Confidence Version 1 Freeze

## Purpose

This document freezes the Version 1 confidence policy used for stock-level allocation control in the paper-only Swing Bot.

Confidence is separate from Opportunity Quality, Entry Score, Opportunity Rank, and frozen Shadow promotion governance.

## Evidence Authority

Confidence must be based on forward completed paper-trade performance for the currently assigned Primary strategy.

The authoritative lifecycle source is the persistent paper trade ledger normalized by `trade_history_manager.py` into completed paper positions. Confidence attribution uses the BUY-side `active_strategy` recorded on the completed trade so entry provenance is preserved.

`results/frozen_strategy_performance.json` is not confidence authority. That artifact is a Primary/Shadow strategy simulation over the available intraday archive and is reserved for frozen strategy comparison/promotion evidence.

Historical research/backtest checkpoints may select a Primary strategy, but they must not be promoted into forward confidence evidence.

Shadow strategy performance is reserved for Primary/Shadow promotion governance and must not directly set stock-level confidence.

An inherited position that was opened under a previous strategy is not credited to a newly assigned Primary merely because the new Primary later becomes exit authority.

## Starting State

A newly admitted mapped candidate with no authoritative forward Primary performance starts at LOW confidence.

Missing performance evidence does not promote or demote confidence.

## Frozen Promotion Thresholds

### LOW to MEDIUM

All of the following are required:

- Win rate >= 40%
- Profit factor >= 1.50
- Completed forward Primary trades >= 15

### MEDIUM to HIGH

All of the following are required:

- Win rate >= 50%
- Profit factor >= 2.00
- Completed forward Primary trades >= 25

## Frozen Demotion Thresholds

### HIGH to MEDIUM

Demotion is eligible when either condition is true:

- Win rate < 45%
- Profit factor < 1.50

### MEDIUM to LOW

Demotion is eligible when either condition is true:

- Win rate < 35%
- Profit factor < 1.25

## Trading Days

Trading-day counts may remain in reports for transparency, but they are informational only.

The legacy 252-day and 504-day confidence promotion requirements do not apply to Version 1 forward Primary confidence.

## Allocation Relationship

The existing stock-level allocation caps remain unchanged:

- HIGH: maximum 25%
- MEDIUM: maximum 15%
- LOW: maximum 7%
- WATCHLIST: 0%

Confidence constrains allocation size. It does not create Opportunity eligibility and does not override the committee sequence.

## Committee Boundaries

The existing committee gates remain unchanged:

- Opportunity Quality >= 70
- Entry Score >= 70
- Thesis intact

Only opportunities that clear committee eligibility may compete for allocation.

Opportunity Rank controls relative allocation among eligible opportunities, subject to confidence and paper-only caps.

## Frozen Strategy Boundary

Primary/Shadow promotion remains governed separately by the frozen five promotion gates:

- Shadow total return > Primary total return
- Three consecutive monthly reviews outperforming Primary
- At least 20 Shadow trades
- Shadow profit factor >= Primary profit factor
- Shadow maximum drawdown <= Primary maximum drawdown + 5 percentage points

A Shadow promotion changes strategy authority only. It does not carry historical Shadow performance into the new Primary's forward allocation confidence unless explicitly governed by a future version.

## Safety

- paper_trade_mode=true
- live trading disabled
- broker execution disabled
- order placement disabled
- capital movement disabled

## Version 1 Change Control

These thresholds and boundaries are frozen for Version 1 QA. Any change requires an explicit versioned architecture decision and must not be introduced by silent retuning.

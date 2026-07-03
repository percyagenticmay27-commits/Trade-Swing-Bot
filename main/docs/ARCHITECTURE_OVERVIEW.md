# TradeBot Swing Trader Architecture Overview

## Purpose

TradeBot_Swing_Trader is a paper-only swing trading and portfolio management system. It discovers opportunities, evaluates confidence and opportunity quality, compares strategies, recommends paper allocations, and summarizes system state.

## Hard Rules

- paper_trade_mode=True always
- No Robinhood execution
- No real order placement
- All trading logic is paper-only
- Reporting outputs should be CSV, JSON, and Markdown where applicable

## Core Layers

1. Data and indicators
2. Paper swing engine
3. Backtesting and optimization
4. Discovery and watchlist lifecycle
5. Confidence engine
6. Strategy Lab
7. Portfolio Allocation Engine
8. Opportunity Quality Engine
9. Executive Dashboard

## Opportunity Quality vs Entry Timing

Opportunity Quality evaluates the attractiveness of an opportunity independently from entry timing. Entry Score is display-only inside the Opportunity Quality Engine and must not affect Opportunity Quality calculations.

## Allocation Meaning

Opportunity rank determines how much capital or percentage allocation an eligible opportunity receives, subject to confidence caps, position caps, theme concentration limits, and SGOV reserve handling.

## Executive Dashboard

The Executive Dashboard reads existing outputs only and creates a high-level review of allocations, confidence, watchlist state, risk flags, and suggested paper-only actions.

# Opportunity Quality Engine Version 1.2 Freeze

## Purpose

The Opportunity Quality Engine is the single source of truth for Opportunity Quality within the TradeBot_Swing_Trader architecture.

It evaluates the attractiveness of an opportunity independently from entry timing.

## Frozen Module

- opportunity_quality_engine.py

## Version 1.2 Component Weightings

- Fundamental Analysis Score: 20%
- Market Intelligence Score: 20%
- Conviction Score: 20%
- Momentum Score: 15%
- Technical Analysis Score: 15%
- Market Regime Support Score: 5%
- Portfolio Risk Adjustment Score: 5%

These weightings are frozen for Version 1.2 QA.

## Permanent Architecture Rules

- Missing evidence = 0
- Entry Score is NOT part of Opportunity Quality
- Entry Score is display-only within this module
- SYSTEM_MODE controls presentation only
- QA and LIVE use identical calculations

## QA Transparency

QA output must expose every component score, every weighting, the final Opportunity Quality score, and the display-only Entry Score gate.

## Paper-Only Enforcement

The module is paper-only. It does not place orders, does not route orders, and does not connect to Robinhood execution.

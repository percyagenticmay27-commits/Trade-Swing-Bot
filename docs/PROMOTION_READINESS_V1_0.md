# Promotion Readiness Version 1.0

## Purpose
Read-only paper-only boundary from WATCHLIST into strategy/paper validation.

## Frozen gates
All six must PASS: Source Confluence >= 5; Financial Health >= 70; Theme Momentum >= 70; Opportunity Quality >= 70; thesis_intact == true; Entry Score >= 70. Gates are independent and are not blended.

## Evidence semantics
PASS = authoritative fresh evidence meets threshold. FAIL = authoritative fresh evidence exists but fails. PENDING = missing, stale, unavailable, or not calculated. PENDING never passes. Missing values are null, never manufactured zero.

## Underlying authority
Company/opportunity evidence resolves by underlying_symbol. Leveraged symbols are paper execution vehicles only: AMZU->AMZN, NFLU->NFLX, NVDX->NVDA, PLTU->PLTR, GGLL->GOOGL, AMDL->AMD, AVL->AVGO.

## Downstream performance
trading_days, number_of_trades, win_rate, profit_factor, paper_return, and max_drawdown are excluded from Promotion Readiness and remain downstream strategy/paper-validation and forward-confidence evidence.

## Compatibility and safety
Legacy Discovery LOW/MEDIUM/HIGH remains unchanged in this migration. Promotion Readiness does not automatically change lifecycle state, activate a strategy, allocate capital, create a position, place an order, move capital, or bypass committee governance.

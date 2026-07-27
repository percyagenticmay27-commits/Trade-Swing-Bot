# Swing Committee Governance

## Purpose

This policy defines the Swing Bot as a sequence of independent, evidence-only decision committees.

A single blended score does not control discovery, opportunity quality, entry timing, allocation, and exit. Each committee has one jurisdiction and may not perform another committee's decision.

## Permanent Principles

- Paper trading only
- Advisory only
- No broker execution
- No capital movement
- No automatic strategy activation
- No stock-name, reputation, sector, theme, or historical-performance bias
- No sector or theme concentration limits
- No market-regime hard veto
- Market regime, sector behavior, and price history may contribute evidence, but they may not become automatic portfolio exclusions
- Entry Score remains independent from Opportunity Quality

## Committee Sequence

```text
Discovery Committee
        ↓
Opportunity Committee
        ↓
Entry Committee
        ↓
Portfolio Committee
        ↓
Exit Committee
```

## Discovery Committee

Question:

> Which securities deserve evidence collection and investigation?

It produces candidates and evidence requests. It does not approve entries, allocate capital, or exit positions.

## Opportunity Committee

Question:

> Does current validated evidence make this an attractive opportunity?

It produces Opportunity Quality, Opportunity Rank, and eligibility. Entry timing is excluded from Opportunity Quality.

Minimum Opportunity Quality remains 70.

## Entry Committee — The Dam Wall

Question:

> Is now an evidence-supported time to deploy paper capital?

The Entry Committee has independent veto authority. A company can have outstanding fundamentals, news, conviction, and Opportunity Quality while still failing entry timing.

Timing evidence includes:

- Daily RSI direction
- Daily Stochastic RSI K/D relationship
- Momentum direction
- Volume confirmation
- Price-trend confirmation
- Extension and pullback risk

Example:

```text
Opportunity Quality: 95 — APPROVED
Entry Score: 45 — REJECTED
Final result: NO POSITION
```

A falling daily RSI or Stochastic RSI K crossing downward can therefore block entry without lowering the company's Opportunity Quality.

Minimum Entry Score remains 70, and the thesis must be intact.

## Portfolio Committee

Question:

> Among entry-approved opportunities, which deserve paper capital and how much?

Rules:

- Higher Opportunity Rank receives greater allocation priority
- No fixed position count is required
- No sector, theme, market-regime, stock-identity, or reputation adjustment is permitted
- No theme concentration cap is permitted
- Unallocated capital remains in SGOV

Only opportunities approved by both Opportunity and Entry may compete for capital.

## Exit Committee

Question:

> Does the held position still deserve paper capital under its assigned strategy?

The Exit Committee applies Strategy A or Strategy B rules. It may not exit solely because of sector membership, theme concentration, or a market-regime label.

A replacement candidate must be a better-ranked opportunity that has independently passed Entry.

## Strategy Relationship

Strategy A and Strategy B retain their different exit and reentry behavior. Both now reference the same independent committee governance:

```text
Opportunity Quality >= 70
Entry Score >= 70
Thesis intact
No Market Regime hard gate
```

Market Regime remains evidence. It is not a mandatory minimum score or automatic veto.

## Files

```text
configs/swing_committee_governance.json
src/swing_trade_bot/swing_committee_governance.py
tests/test_swing_committee_governance.py
```

Optional generated output:

```text
results/swing_committee_governance.json
```

## Validation

Run from the `main` directory:

```cmd
python -m py_compile src\swing_trade_bot\swing_committee_governance.py
pytest tests\test_swing_committee_governance.py -v

python -m py_compile src\swing_trade_bot\swing_strategy_capability_profiles.py
pytest tests\test_swing_strategy_capability_profiles.py -v
```

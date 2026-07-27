# Swing Strategy Capability Profiles

## Purpose

Phase 9E.2 publishes machine-readable capability profiles for Strategy A and Strategy B independently of the Swing plugin registration.

The profiles now reference the independent committee-governance policy defined in:

```text
configs/swing_committee_governance.json
```

## Outputs

```text
configs/swing_strategy_capability_profiles.json
results/swing_strategy_capability_profiles.json
```

## Shared Entry Governance

Opportunity and Entry answer different questions and are never blended.

```text
Opportunity Quality >= 70
Entry Score >= 70
Thesis intact
```

Entry is an independent timing veto. Market Regime remains usable evidence, but there is no mandatory Market Regime minimum and no market-regime hard gate.

The Entry Committee may reject an otherwise excellent company when daily timing evidence is deteriorating, including falling RSI, bearish Stochastic RSI K/D behavior, weakening momentum, poor volume confirmation, trend failure, or excessive extension.

## Strategy A

- Purpose: thesis preservation
- Risk style: moderate
- Capital protection: medium
- Supported assets: stocks and leveraged ETFs
- Reentry support: no
- No hard numerical loss exit
- Exit review is driven by thesis and evidence deterioration
- Sector, theme, or Market Regime alone may not force exit

## Strategy B

- Purpose: capital protection and reentry
- Risk style: conservative
- Capital protection: high
- Supported assets: stocks and leveraged ETFs
- Reentry support: yes
- A 10% paper drawdown triggers exit/reentry review
- Reentry requires a three-day wait, intact thesis, Opportunity Quality 70, Entry Score 70, and price within 3% of the reentry level
- Reentry has no mandatory Market Regime minimum
- Sector, theme, or Market Regime alone may not force exit

## Shared Profit Protection

```text
Standard gain zone: 20%
Standard giveback review: 5%
Strong gain zone: 30%
Strong giveback review: 10%
```

These are review thresholds, not automatic brokerage orders.

## Evidence-Only Policy

The profiles do not permit allocation or exit bias based on:

- stock identity or popularity
- historical reputation
- sector or theme
- theme concentration
- market-regime label

Sector, theme, Market Regime, and historical price behavior may contribute evidence to current scores, but they do not create automatic exclusions, quotas, or concentration caps.

## Safety

```text
paper_trade_mode=True
advisory_only=True
automatic_activation_allowed=False
```

The module does not place orders, connect to Robinhood, move capital, activate a strategy, or write to the CIO database.

## Validation

Run from the `main` directory in Git CMD:

```cmd
python -m py_compile src\swing_trade_bot\swing_strategy_capability_profiles.py
python -m pytest tests\test_swing_strategy_capability_profiles.py -v
```

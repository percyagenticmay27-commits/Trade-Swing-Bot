# Swing Strategy Capability Profiles

## Purpose

Phase 9E.2 publishes machine-readable capability profiles for Strategy A and Strategy B independently of the Swing plugin registration.

The CIO can use these profiles to understand strategy behavior before showing or allocating paper capital to a strategy family.

## Output

Source configuration:

```text
configs/swing_strategy_capability_profiles.json
```

Optional generated output:

```text
results/swing_strategy_capability_profiles.json
```

## Strategy A

- Purpose: thesis preservation
- Risk style: moderate
- Capital protection: medium
- Supported assets: stocks and leveraged ETFs
- Reentry support: no
- Entry review requires Opportunity Quality 70, Entry Score 70, Market Regime 50, and an intact thesis
- No hard numerical loss exit is declared
- Exit review is driven by thesis, opportunity quality, quality trend, market regime, and profit-giveback evidence

## Strategy B

- Purpose: capital protection and reentry
- Risk style: conservative
- Capital protection: high
- Supported assets: stocks and leveraged ETFs
- Reentry support: yes
- Entry review requires Opportunity Quality 70, Entry Score 70, Market Regime 50, and an intact thesis
- A 10% paper drawdown triggers exit/reentry review
- Reentry requires a three-day wait, intact thesis, Opportunity Quality 70, Entry Score 70, Market Regime 50, and price within 3% of the reentry level

## Shared Profit Protection

Both profiles advertise:

```text
Standard gain zone: 20%
Standard giveback review: 5%
Strong gain zone: 30%
Strong giveback review: 10%
```

These are review thresholds, not automatic brokerage orders.

## CIO Uses

The capability profile allows the CIO to:

- filter strategies by supported asset type
- identify reentry-capable strategies
- compare capital-protection levels
- explain strategy behavior to the investor
- validate that a strategy profile matches the frozen Swing policy
- block future ungoverned strategy profiles

## Safety

Permanent rules:

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

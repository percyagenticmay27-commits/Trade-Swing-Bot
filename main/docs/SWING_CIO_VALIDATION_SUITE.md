# Swing CIO Validation Suite

## Purpose

Phase 9F validates the complete Trade Swing Bot CIO compatibility boundary as one paper-only enterprise system.

The suite does not place orders, connect to Robinhood, move capital, activate strategies, modify policy, or write to the CIO database.

## Validated Components

- CIO Plugin Manifest
- CIO Output Contract
- CIO Schema Registry
- CIO Presentation Adapter
- Enterprise Strategy Service Registration
- Strategy Capability Profiles
- Independent Committee Governance
- Committee Decision Traceability
- Governed Committee Learning

## Validation Areas

### Identity

All CIO-facing components must use:

```text
SWING-001
```

### Committee Governance

The frozen sequence is:

```text
Discovery
Opportunity
Entry
Portfolio
Exit
```

Entry remains independent from Opportunity Quality and may veto an otherwise high-quality opportunity.

### Traceability

The suite verifies deterministic and append-only traceability configuration, frozen committee order, and explicit bias-audit fields.

### Learning

Minimum evidence remains:

```text
30 completed decision traces
6 months of history
10 observations per committee
```

Learning remains advisory and cannot change policy automatically.

### Evidence-Only Allocation

The required audit fields are:

```text
sector_bias_applied=False
theme_bias_applied=False
concentration_limit_applied=False
stock_history_bias_applied=False
market_regime_veto_applied=False
```

### Safety

Permanent safety requirements include:

```text
paper_trade_mode=True
advisory_only=True
read_only=True
append_only_learning=True
automatic_policy_change_allowed=False
broker_execution_allowed=False
capital_movement_allowed=False
robinhood_execution_allowed=False
```

## Governance Health Score

The strict pass/fail result remains authoritative. The health score provides an executive summary across:

- Identity
- Components
- Governance
- Traceability
- Learning
- Safety

A system is `READY` only when there are no validation errors.

## Outputs

```text
results/swing_cio_validation_report.json
results/swing_cio_validation_report.md
```

## Local Validation

Run from the `main` directory:

```cmd
python -m py_compile src\swing_trade_bot\swing_cio_validation_suite.py
python -m pytest tests\test_swing_cio_validation_suite.py -v
```

Then run the full CIO committee and validation group:

```cmd
python -m pytest tests\test_swing_committee_governance.py tests\test_swing_strategy_capability_profiles.py tests\test_swing_committee_traceability.py tests\test_swing_committee_learning.py tests\test_swing_cio_validation_suite.py -v
```

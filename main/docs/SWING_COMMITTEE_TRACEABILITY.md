# Swing Committee Decision Traceability

## Purpose

Phase 9E.4 records the complete paper-only decision path for every evaluated security while preserving exactly what each committee knew, decided, and cited at the time of evaluation.

The design follows the Dividend Bot's append-only learning-record pattern:

- deterministic SHA-256 record keys
- stable trace and step identifiers
- source-artifact lineage
- immutable original decisions
- separately appended later outcomes
- duplicate outcome suppression
- advisory recommendations only
- no automatic policy changes

## Committee path

```text
Discovery
    ↓
Opportunity
    ↓
Entry
    ↓
Portfolio
    ↓
Exit
```

Each committee step records:

- committee ID and frozen sequence
- pass, fail, veto, skip, review, hold, or exit status
- reason codes
- complete evidence snapshot
- source artifacts
- deterministic input-snapshot hash
- deterministic step ID

## Entry-wall trace

A strong opportunity may still be rejected by Entry:

```text
Opportunity Quality: 95 — PASS
Entry Score: 42 — VETO
Portfolio Committee: SKIPPED
Final Status: WAIT
```

The trace preserves that the company remained a strong opportunity and was rejected only because current entry timing was not supported.

## Bias audit

Every trace must explicitly record the following as `false`:

```text
sector_bias_applied
 theme_bias_applied
concentration_limit_applied
stock_history_bias_applied
market_regime_veto_applied
```

Sector, theme, market regime, and history may appear as evidence, but none may act as an automatic quota, prejudice, concentration rule, or hard veto.

## Outcome attachments

Later paper outcomes are appended separately and never rewrite the original decision. Example measurement horizons include:

- 3 trading days
- 5 trading days
- 10 trading days
- 20 trading days
- position close

Outcome metrics may include return, maximum favorable excursion, maximum adverse excursion, drawdown, thesis outcome, and whether the committee decision was effective.

Each outcome receives a deterministic record key and outcome ID. Duplicate record keys are ignored during append operations.

## Outputs

Suggested paths:

```text
results/decision_traces/<evaluation_cycle_id>/<symbol>.json
results/committee_outcomes.json
```

## Safety

Permanent rules:

```text
paper_trade_mode=True
advisory_only=True
append_only=True
automatic_policy_change_allowed=False
broker_execution_allowed=False
capital_movement_allowed=False
```

The module does not place orders, communicate with Robinhood, move capital, activate strategies, or rewrite production policy.

## Validation

Run from the `main` directory:

```cmd
python -m py_compile src\swing_trade_bot\swing_committee_traceability.py
python -m pytest tests\test_swing_committee_traceability.py -v
```

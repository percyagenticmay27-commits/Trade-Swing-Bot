# Swing CIO Acceptance Test

## Purpose

Phase 9F.1 performs an end-to-end, paper-only acceptance test of the Swing Bot CIO contract after Phase 9F reports the repository as READY.

## Acceptance Flow

```text
Enterprise Discovery
        ↓
Plugin Registration
        ↓
Full CIO Validation
        ↓
Committee Governance
        ↓
Decision Trace Replay
        ↓
Learning Governance
        ↓
Safety Boundary
        ↓
READY_FOR_CIO
```

## Required Conditions

- Plugin identity is `SWING-001`.
- Strategy registration is paper-compatible.
- Governance review is required.
- Automatic activation is disabled.
- Phase 9F status is `READY`.
- Governance health score is 100.
- Strategy A and Strategy B are both registered.
- The frozen five-committee order remains intact.
- A stored committee decision trace can be replayed without changing its path, statuses, reason codes, or evidence snapshot hashes.
- Committee learning remains append-only, advisory-only, and human-approved.
- No automatic policy changes are allowed.
- No broker execution, Robinhood execution, capital movement, or direct database writes are allowed.

## Outputs

```text
results/swing_cio_acceptance_report.json
results/swing_cio_acceptance_report.md
```

## Final Results

```text
READY_FOR_CIO
NOT_READY_FOR_CIO
```

Any failed acceptance stage produces `NOT_READY_FOR_CIO`.

## Safety

The acceptance test is read-only, paper-only, and advisory-only. It does not place orders, connect to a broker, move capital, activate strategies, or write to the CIO database.

## Validation

Run from the `main` directory:

```cmd
python -m py_compile src\swing_trade_bot\swing_cio_acceptance_test.py
python -m pytest tests\test_swing_cio_acceptance_test.py -v
```

# Swing CIO Acceptance Registration Compatibility Fix

Date: 2026-08-12
Branch: `feature/swing-phase2-enterprise-market-data`

## Runtime failure observed

A successful Swing-owned market-data refresh and strategy-report cycle reached CIO acceptance but stopped with:

- `PLUGIN_REGISTRATION`: FAIL
- `CIO_ACCEPTANCE`: FAIL
- `MILESTONE_1_FREEZE`: FAIL
- `LOCAL_FILESYSTEM_REGISTRATION`: FAIL

The generated registration was otherwise valid and paper-safe.

## Root cause

The current Swing service registration publishes:

`governance_review_required: true`

The older CIO acceptance module still required only the legacy field:

`governance_required: true`

Therefore the acceptance stage rejected the current registration even though governance review remained required.

## Fix

`src/swing_trade_bot/swing_cio_acceptance_test.py` now resolves both registration forms:

- current: `governance_review_required`
- legacy: `governance_required`

Compatibility is fail-closed:

- either single field may establish required governance;
- when both fields are supplied, both must be `true`;
- conflicting fields fail CIO acceptance.

No paper-only or governance requirement was weakened.

## Regression coverage

`tests/test_swing_cio_acceptance_test.py` now uses the current registration field and proves:

1. current `governance_review_required=true` is accepted;
2. legacy `governance_required=true` remains accepted;
3. conflicting current/legacy governance fields fail closed;
4. existing registration, validation, committee, learning, replay, and safety failure tests remain in place.

## Safety invariants preserved

- `paper_trade_mode=true`
- advisory-only
- no broker execution
- no Robinhood execution
- no capital movement
- no direct database writes
- automatic activation remains disabled

## Next server validation

Pull the branch to `/home/tradebot/Trade-Swing-Bot/main`, compile the acceptance module, run `tests/test_swing_cio_acceptance_test.py`, then rerun `python run_swing_bot_cycle.py` only if the focused acceptance tests pass.

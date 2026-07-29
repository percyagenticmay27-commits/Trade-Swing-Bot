# Swing Daily Cycle

## Purpose

`run_swing_bot_cycle.py` is the authoritative paper-only orchestration launcher for the Trade Swing Bot.

It coordinates the existing strategy-report outputs and CIO governance artifacts in one deterministic cycle. It does not connect to a broker, place an order, move capital, change strategy policy, or write to PostgreSQL.

## Command

From the Python project root:

```bash
python run_swing_bot_cycle.py
```

Equivalent module command:

```bash
python -m swing_trade_bot.swing_daily_cycle
```

The project root on the deployment server is expected to be:

```text
/home/tradebot/Trade-Swing-Bot/main
```

## Cycle order

1. Validate `configs/swing_daily_cycle.json`.
2. Atomically publish the frozen CIO manifest, output contract, schema registry, strategy registration, capability profiles, and committee governance artifacts.
3. Confirm the strategy-owned reports are present.
4. Build and publish the Phase 9F CIO validation report.
5. Build and publish the Phase 9F.1 acceptance report.
6. Build and publish the Milestone 1 freeze report.
7. Publish `swing_local_filesystem_registration.json` last and only when every readiness gate passes.
8. Always write the daily-cycle JSON and Markdown report.

## Registration-last rule

The AI CIO uses the local registration as the completed-cycle discovery signal. The registration is not published when any of the following is true:

- a required strategy report is missing;
- the committee decision trace is missing;
- Phase 9F is not `READY`;
- Phase 9F.1 is not `READY_FOR_CIO`;
- Milestone 1 is not `FROZEN`;
- the local-filesystem configuration is invalid.

All JSON and Markdown publications use a sibling `.tmp` file followed by `fsync` and atomic replacement. The AI CIO should ignore `.tmp` files.

## Required strategy-owned reports

Version 1.0 of the cycle requires:

```text
results/opportunity_quality.json
results/executive_dashboard.json
results/monthly_command_center.json
results/swing_committee_decision_trace.json
```

These reports remain owned by their existing engines. The cycle coordinates and validates them; it does not fabricate missing market evidence or trading decisions.

## Outputs

```text
results/swing_daily_cycle_report.json
results/swing_daily_cycle_report.md
results/swing_cio_validation_report.json
results/swing_cio_validation_report.md
results/swing_cio_acceptance_report.json
results/swing_cio_acceptance_report.md
results/swing_cio_milestone_1_freeze.json
results/swing_cio_milestone_1_freeze.md
results/swing_local_filesystem_registration.json
```

The daily-cycle status is:

- `COMPLETE` when the registration was safely published last;
- `BLOCKED` when any readiness dependency failed or is missing.

A blocked cycle exits with process status `1` so systemd can record the failure. A complete cycle exits with status `0`.

## Permanent safety boundaries

- `paper_trade_mode=True`
- `advisory_only=True`
- no Robinhood execution
- no broker execution
- no order placement
- no capital movement
- no direct database writes
- no automatic activation
- no automatic policy changes

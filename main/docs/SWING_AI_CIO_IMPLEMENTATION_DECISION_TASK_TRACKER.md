# Swing Bot → Enterprise AI CIO Implementation Decision & Task Tracker

Last updated: 2026-08-12

## Purpose

This document is the Swing-repository continuity record for implementing `SWING-001` against the current Enterprise AI CIO filesystem/JSON contract. A new Trade Swing Bot chat must read this document before making integration changes so completed work is not repeated and architecture boundaries are preserved.

Authoritative external handoff reviewed on 2026-08-12: `SWING_BOT_TO_AI_CIO_IMPLEMENTATION_HANDOFF.md` supplied by the AI CIO/Dividend host workstream.

## Non-negotiable architecture decisions

- Strategy identity remains `SWING-001`.
- Swing is an external, independently deployable, paper-only/advisory-only strategy plugin.
- Governed Enterprise allocation remains `$4,500.00` unless changed by AI CIO allocation governance.
- Swing must never place live orders, enable broker execution, move capital, automatically activate live trading, or directly write the AI CIO database.
- Swing must not import Dividend Bot production code or write to `/home/tradebot/Trade-Dividend-Bot/results/` or `/home/tradebot/Trade-Dividend-Bot/configs/`.
- AI CIO owns registry construction, external registration ingestion, discovery, validation, dashboards, and allocation governance.
- Swing owns strategy logic, market data, paper state, reports/evidence, its own service/timer, and its own `results/` publication.
- Missing/unknown metrics remain unavailable/null/not reported. They must not be fabricated or converted to zero.
- Enterprise allocation must not be substituted for actual portfolio value or counted as realized performance.
- Publication must be atomic so AI CIO cannot consume half-written JSON.

## Authoritative runtime locations

- Repository: `/home/tradebot/Trade-Swing-Bot/main`
- Virtual environment: `/home/tradebot/Trade-Swing-Bot/main/.venv`
- Registration: `/home/tradebot/Trade-Swing-Bot/main/configs/swing_strategy_service_registration.json`
- Swing evidence root: `/home/tradebot/Trade-Swing-Bot/main/results/`
- AI CIO host: `/home/tradebot/Trade-Dividend-Bot`

## Audit completed in this chat

### Registration

The current `configs/swing_strategy_service_registration.json` was inspected on branch `feature/swing-phase2-enterprise-market-data`.

Confirmed:

- `strategy_id`, `plugin_id`, and `service_id` are `SWING-001`.
- `paper_trade_mode=true`.
- `advisory_only=true`.
- `live_trading_enabled=false`.
- `broker_execution_enabled=false`.
- `capital_movement_enabled=false`.
- `automatic_activation_allowed=false`.
- `direct_database_writes=false`.
- The registration declares 12 AI CIO dashboard capabilities/artifacts.

Gap found:

- The new AI CIO handoff says artifact paths should be relative to `repository_root`, but the current registration stores absolute paths and does not currently declare `repository_root`. This must be reconciled carefully with the receiving contract before changing the registration.

### Existing unified daily cycle

`src/swing_trade_bot/swing_daily_cycle.py` already exists and already implements a substantial portion of the required unified paper-cycle architecture.

Confirmed existing behavior:

- paper-only/advisory safety configuration validation;
- atomic JSON publication through the local filesystem integration helper;
- atomic text publication with flush, `fsync`, and `os.replace`;
- committee runtime evidence and decision trace generation;
- Opportunity Quality generation;
- Stock Performance generation;
- Weekly Stock Report generation;
- Executive Dashboard generation;
- Monthly Command Center generation;
- cycle report generation;
- readiness/validation/acceptance/freeze processing;
- registration publication only after readiness.

The existing server launcher `run_swing_bot_cycle.py` is also confirmed. It runs the Swing daily cycle and, only after a successful cycle, publishes Enterprise KPI v2.1 evidence. This is the leading candidate for the real systemd `ExecStart`; do not invent another launcher without evidence that this one is unsuitable.

### Existing Enterprise KPI publisher

`src/swing_trade_bot/enterprise_strategy_kpi_publisher_v21.py` already provides:

- `SWING-001` KPI v2.1 construction;
- allocation provenance preservation;
- paper/broker/capital safety constants;
- atomic KPI writes using a same-directory temporary file, flush, `fsync`, and `os.replace`;
- dashboard sections for portfolio, holdings, performance, watchlist, opportunity quality, and trade history;
- an artifact contract for several underlying Swing evidence files.

Important mismatch found:

- Its internal `ARTIFACT_SPECS` currently references `opportunity_quality.json`, while the current AI CIO registration/handoff declares `opportunity_quality_report.json`.
- Its internal artifact contract focuses on KPI underlying evidence and is not identical to the 12-artifact external registration contract. Do not assume these two contracts are interchangeable.

## Current declared AI CIO publication surface

The registration currently declares:

1. `results/enterprise_strategy_kpis.json`
2. `results/executive_dashboard.json`
3. `results/portfolio_allocations.json`
4. `results/watchlist_report.json`
5. `results/swing_daily_cycle_report.json`
6. `results/market_data_refresh_status.json`
7. `results/monthly_command_center.json`
8. `results/opportunity_quality_report.json`
9. `results/portfolio_risk.json`
10. `results/position_lifecycle.json`
11. `results/stock_performance_report.json`
12. `results/weekly_stock_report.json`

## Gap analysis after first repository audit

### Already wired into the unified cycle

- `results/swing_daily_cycle_report.json`
- `results/opportunity_quality_report.json`
- `results/stock_performance_report.json`
- `results/weekly_stock_report.json`
- `results/executive_dashboard.json`
- `results/monthly_command_center.json`
- `results/enterprise_strategy_kpis.json` is published by `run_swing_bot_cycle.py` after a successful daily cycle.

### Used as an input / expected to exist

- `results/portfolio_allocations.json`
- `results/watchlist_report.json`

These require producer/freshness verification. The unified cycle currently consumes them but the audited section does not prove that it refreshes them during the same completed cycle.

### Declared but producer still needs to be located/verified

- `results/market_data_refresh_status.json`
- `results/portfolio_risk.json`
- `results/position_lifecycle.json`

Do not create placeholder evidence. Locate an authentic existing producer first. If the capability is unsupported, the correct fix is to remove the declaration rather than fabricate data.

## Implementation tasks

### Task A — Complete producer mapping

Status: **IN PROGRESS**

- [x] Inspect external AI CIO handoff.
- [x] Inspect Swing service registration.
- [x] Inspect unified Swing daily cycle.
- [x] Inspect Enterprise KPI v2.1 publisher.
- [x] Confirm existing authoritative launcher candidate: `run_swing_bot_cycle.py`.
- [ ] Locate the producer for `portfolio_allocations.json` and prove it refreshes in the same cycle.
- [ ] Locate the producer for `watchlist_report.json` and prove it refreshes in the same cycle.
- [ ] Locate the producer for `market_data_refresh_status.json`.
- [ ] Locate the producer for `portfolio_risk.json`.
- [ ] Locate the producer for `position_lifecycle.json`.
- [ ] Compare every registration declaration against a real producer and remove unsupported declarations rather than creating placeholders.

### Task B — Reconcile the external registration contract

Status: **NOT STARTED**

- [ ] Add/verify `repository_root=/home/tradebot/Trade-Swing-Bot/main` if required by the current receiving contract.
- [ ] Reconcile current absolute artifact paths with the handoff requirement for paths relative to `repository_root`.
- [ ] Preserve all paper/advisory safety locks.
- [ ] Keep registration capability declarations synchronized with genuinely generated artifacts.
- [ ] Add regression tests for registration path resolution and safety locks.

### Task C — Same-cycle unified publication

Status: **PARTIALLY IMPLEMENTED**

- [x] Existing unified cycle architecture is present.
- [x] Atomic JSON/text publication infrastructure exists.
- [ ] Ensure market refresh occurs before strategy/report publication.
- [ ] Ensure portfolio allocations and watchlist are refreshed from authoritative current-cycle data rather than merely consumed from older files.
- [ ] Wire every supported declared artifact into the same successful paper cycle.
- [ ] Ensure required publication failure causes a nonzero cycle exit.
- [ ] Validate timestamps/freshness and `SWING-001` ownership before final publication.

### Task D — Canonical KPI alignment

Status: **PARTIALLY IMPLEMENTED**

- [x] KPI v2.1 publisher exists.
- [x] Allocation provenance is preserved.
- [x] KPI writes are atomic.
- [ ] Reconcile `opportunity_quality.json` vs `opportunity_quality_report.json` in the KPI artifact specification.
- [ ] Verify `$4,500.00` comes from governed allocation evidence and is not silently redefined by Swing.
- [ ] Verify unknown performance values remain null/not reported.
- [ ] Verify allocation is never used as realized P&L or inferred performance.
- [ ] Verify watchlist count exactly matches the current published watchlist.
- [ ] Add/extend KPI regression tests for the new AI CIO handoff contract.

### Task E — Required Swing regression QA

Status: **NOT STARTED FOR THIS HANDOFF**

Add/verify tests proving:

- [ ] every supported declared artifact is generated by a successful paper cycle;
- [ ] every declared JSON parses;
- [ ] ownership is `SWING-001` where the artifact schema carries strategy ownership;
- [ ] missing optional metrics remain unavailable/null rather than zero;
- [ ] paper-only and broker-disabled flags cannot be relaxed;
- [ ] publisher writes are atomic;
- [ ] same-cycle reruns are deterministic/idempotent where appropriate;
- [ ] governed allocation remains `$4,500.00` and is not performance;
- [ ] watchlist count matches the published watchlist;
- [ ] stale market data is clearly identified;
- [ ] Swing imports no Dividend production code;
- [ ] Swing writers cannot modify AI CIO host repository paths.

### Task F — Swing-owned systemd deployment

Status: **NOT STARTED**

- [x] Existing launcher candidate identified: `/home/tradebot/Trade-Swing-Bot/main/run_swing_bot_cycle.py`.
- [ ] Verify launcher successfully completes the full publication contract before systemd installation.
- [ ] Create a Swing-owned oneshot service using the Swing working directory and `.venv`.
- [ ] Create a separate Swing timer.
- [ ] Do not modify `dividend-bot.service` or `dividend-allocation.service` to execute Swing.
- [ ] Verify service/timer status and journal output.

### Task G — End-to-end AI CIO acceptance

Status: **NOT STARTED**

After Swing publication succeeds:

- [ ] refresh the AI CIO registry from the Dividend host only as a receiving-side verification step;
- [ ] restart `dividend-allocation.service` if required by the handoff;
- [ ] confirm `SWING-001` remains registered and `AVAILABLE`;
- [ ] confirm governed allocation remains `$4,500.00`;
- [ ] confirm evidence paths resolve under `/home/tradebot/Trade-Swing-Bot/main/results/`;
- [ ] confirm watchlist/portfolio/opportunity/risk/lifecycle/performance displays use actual Swing evidence;
- [ ] inspect remaining `SWING-001` missing-artifact warnings and fix the Swing producer/registration rather than suppressing AI CIO warnings.

## Evidence required before declaring integration complete

Return one final evidence package containing:

1. Swing `git status --short` and commit SHA;
2. exact tests run and complete pass count;
3. Swing service status;
4. Swing timer status;
5. declared-artifact validation output;
6. AI CIO `SWING-001` inspection output;
7. remaining `SWING-001` missing-artifact warnings, if any;
8. explicit confirmation that no Dividend repository files were modified by Swing development.

## Continuation instruction for a new chat

If this work moves to a new Trade Swing Bot chat:

1. Read this tracker first.
2. Read the latest AI CIO handoff supplied by the user.
3. Work only in the Swing repository/branch authorized by the user.
4. Resume at the first unchecked task above; do not rebuild completed components.
5. Preserve paper-only safety and the AI CIO/Swing repository boundary.
6. Update this tracker whenever a task is completed, a contract decision changes, or a new blocker is discovered.

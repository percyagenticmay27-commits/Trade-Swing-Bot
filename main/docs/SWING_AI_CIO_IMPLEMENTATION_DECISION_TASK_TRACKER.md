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

## Completed development in this implementation pass

### External registration contract aligned

`configs/swing_strategy_service_registration.json` was updated to the current AI CIO repository-root contract.

Completed:

- Added `repository_root=/home/tradebot/Trade-Swing-Bot/main`.
- Converted declared dashboard artifact paths from absolute paths to paths relative to `repository_root`.
- Converted manifest/presentation references to repository-relative paths.
- Added explicit `order_placement_enabled=false` safety lock.
- Preserved `paper_trade_mode=true`, `advisory_only=true`, `live_trading_enabled=false`, `broker_execution_enabled=false`, `capital_movement_enabled=false`, `automatic_activation_allowed=false`, and `direct_database_writes=false`.
- Registration version advanced to `1.5`.
- Added `tests/test_swing_strategy_service_registration_contract.py` to verify repository root, exact relative publication surface, path containment, and safety locks.

### Canonical KPI opportunity-quality path aligned

`src/swing_trade_bot/enterprise_strategy_kpi_publisher_v21.py` was updated so its Opportunity Quality evidence path agrees with both the daily cycle and current AI CIO registration.

Completed:

- Replaced internal `opportunity_quality.json` expectation with `opportunity_quality_report.json`.
- `strategy_intelligence.opportunity_quality_evidence` now loads from `opportunity_quality_report.json`.
- KPI module version advanced to `2.1.5`.
- Added regression coverage proving `opportunity_quality_report.json` is recognized in the KPI artifact contract and evidence section.

## Existing unified daily cycle confirmed

`src/swing_trade_bot/swing_daily_cycle.py` already implements a substantial part of the target architecture:

- paper-only/advisory safety config validation;
- atomic JSON publication;
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

`run_swing_bot_cycle.py` remains the leading authoritative server launcher candidate. It runs the Swing daily cycle and publishes Enterprise KPI v2.1 only after the cycle succeeds. Do not invent another launcher without evidence that this one is unsuitable.

## Current declared AI CIO publication surface

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

## Producer mapping status

### Already wired into the unified cycle

- `results/swing_daily_cycle_report.json`
- `results/opportunity_quality_report.json`
- `results/stock_performance_report.json`
- `results/weekly_stock_report.json`
- `results/executive_dashboard.json`
- `results/monthly_command_center.json`
- `results/enterprise_strategy_kpis.json` via `run_swing_bot_cycle.py` after successful cycle completion.

### Used as input / freshness still must be proven

- `results/portfolio_allocations.json`
- `results/watchlist_report.json`

The audited daily-cycle path consumes these files, but current evidence does not yet prove that both are refreshed during the same completed cycle.

### Declared producer still unresolved

- `results/market_data_refresh_status.json`
- `results/portfolio_risk.json`
- `results/position_lifecycle.json`

Do not create placeholders. Locate an authentic producer. If a capability is unsupported, remove the declaration instead of fabricating evidence.

## Implementation tasks

### Task A — Complete producer mapping

Status: **IN PROGRESS**

- [x] Inspect external AI CIO handoff.
- [x] Inspect Swing service registration.
- [x] Inspect unified Swing daily cycle.
- [x] Inspect Enterprise KPI v2.1 publisher.
- [x] Confirm authoritative launcher candidate: `run_swing_bot_cycle.py`.
- [ ] Locate the producer for `portfolio_allocations.json` and prove it refreshes in the same cycle.
- [ ] Locate the producer for `watchlist_report.json` and prove it refreshes in the same cycle.
- [ ] Locate the producer for `market_data_refresh_status.json`.
- [ ] Locate the producer for `portfolio_risk.json`.
- [ ] Locate the producer for `position_lifecycle.json`.
- [ ] Compare every declaration against a real producer and remove unsupported declarations rather than creating placeholders.

### Task B — Reconcile the external registration contract

Status: **IMPLEMENTED — SERVER VALIDATION PENDING**

- [x] Add `repository_root=/home/tradebot/Trade-Swing-Bot/main`.
- [x] Convert registered dashboard artifact paths to paths relative to `repository_root`.
- [x] Preserve and extend paper/advisory safety locks, including explicit order-placement disablement.
- [x] Add regression tests for path resolution contract and safety locks.
- [ ] Confirm the AI CIO host accepts the updated registration after DigitalOcean pull/validation.
- [ ] Keep capability declarations synchronized with producer findings from Task A.

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

Status: **IN PROGRESS**

- [x] KPI v2.1 publisher exists.
- [x] Allocation provenance is preserved.
- [x] KPI writes are atomic.
- [x] Reconcile `opportunity_quality_report.json` with the external registration contract.
- [x] Add KPI regression coverage for the registered Opportunity Quality filename.
- [ ] Verify `$4,500.00` comes from governed allocation evidence and is not silently redefined by Swing in the full daily cycle.
- [ ] Verify unknown performance values remain null/not reported.
- [ ] Verify allocation is never used as realized P&L or inferred performance.
- [ ] Verify watchlist count exactly matches the current published watchlist.

### Task E — Required Swing regression QA

Status: **STARTED**

- [x] Registration repository-root and relative-path contract test added.
- [x] Registration safety-lock test added.
- [x] KPI Opportunity Quality artifact-path test added.
- [ ] every supported declared artifact is generated by a successful paper cycle;
- [ ] every declared JSON parses;
- [ ] ownership is `SWING-001` where the schema carries strategy ownership;
- [ ] missing optional metrics remain unavailable/null rather than zero;
- [ ] paper-only and broker-disabled flags cannot be relaxed across the complete publication surface;
- [ ] publisher writes are atomic across the complete surface;
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
- [ ] inspect remaining `SWING-001` missing-artifact warnings and fix Swing producer/registration rather than suppressing AI CIO warnings.

## Commits from this implementation pass

- `80386f7baaca9dab327fc2af0d93e77fe1e21cc8` — initial AI CIO implementation decision/task tracker.
- `112741fa7af15253da5dcfb04bee665e9016d457` — align registration with repository-root/relative-path contract.
- `89bbd0ddaebcc014a8369baa42ebf26b5ec28fd5` — align KPI Opportunity Quality artifact filename.
- `b20814d7317932438391d26f87e7d48f1e54e049` — KPI contract regression test.
- `3fff72b136cc698ede27d476c41ad77e6ac1e4e8` — registration contract regression tests.

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

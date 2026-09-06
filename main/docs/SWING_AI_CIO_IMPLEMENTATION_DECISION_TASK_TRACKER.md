# Swing Bot → Enterprise AI CIO Implementation Decision & Task Tracker

Last updated: 2026-08-13

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

## 2026-08-13 milestone — Swing Runtime Evidence Refresh and Authority Alignment

Status: **COMPLETE AND FROZEN**

This milestone repaired the daily runtime pipeline so current authoritative Swing evidence is regenerated and consumed in dependency order rather than mixing current reports with stale watchlist, allocation, committee, or paper-ledger evidence.

### Frozen runtime ordering

The validated dependency order is now:

1. Current Swing market data / symbol resolution
2. Current watchlist refresh
3. Opportunity Quality input assembly
4. Opportunity Quality calculation
5. Committee runtime evidence
6. Committee decision trace
7. Current stock-level portfolio allocation
8. Paper portfolio mark-to-market / ledger evidence refresh
9. Trade-history and paper-performance analytics
10. Stock Performance
11. Weekly Stock Report
12. Executive Dashboard
13. Monthly Command Center
14. CIO validation / acceptance / freeze evidence
15. Registration publication last
16. Enterprise KPI v2.1 publication after successful cycle completion

Do not regress this order by moving committee evaluation ahead of current Opportunity Quality generation.

### Runtime evidence authority rules now frozen

- Opportunity Quality remains Version 1.2 with frozen component weights and `missing evidence = 0`.
- Entry Score remains display-only and independent from Opportunity Quality.
- Current watchlist screening statistics are candidate lifecycle evidence only; they are not strategy-wide performance.
- Strategy win rate must come from authoritative completed paper trades. With zero closed trades, `win_rate_percent` is `null` / not reportable.
- Current position allocation comes from the Portfolio Manager `allocation_before` field.
- Target position allocation comes from `portfolio_allocations.json` `allocation_percent`.
- Portfolio action comes from Portfolio Manager `action`/rebalance evidence.
- Existing SOXL/TQQQ paper positions are marked to current market evidence; they are not recreated on daily-cycle reruns.
- Existing BUY transactions remain idempotent and are not duplicated by report refresh.
- Strategy-level `$4,500.00` allocation remains externally governed by AI CIO evidence discovery and is distinct from stock-level allocations and actual portfolio value.
- No dashboard value may be manufactured to make the UI appear populated.

### Validated runtime values at milestone freeze

Validated on DigitalOcean after a successful current cycle:

- Full Swing regression suite: `965 passed, 1 skipped`.
- Daily cycle status: `COMPLETE`.
- Cycle stages: `15/15 PASS`.
- Opportunity symbol: `NBIS`.
- Opportunity Quality: `15.458`.
- Opportunity Committee sees `15.458` with `score_available=true` and correctly returns `FAIL` because the configured minimum is `70.0`.
- Entry Score: `0.0`; Entry Committee is correctly `SKIPPED` after Opportunity rejection.
- Open paper positions: `2` (`SOXL`, `TQQQ`).
- Paper portfolio value: `$4,525.52`.
- Positions market value: `$1,825.52`.
- Unrealized paper P&L: `+$25.52`.
- Paper portfolio return: `+0.567111%`.
- Closed paper trades: `0`.
- Authoritative strategy win rate: `null` / not reportable.
- Governed Enterprise allocation: `$4,500.00`.
- Allocation source: `AI_CIO_ENTERPRISE_EVIDENCE`.
- Market-data status: `AVAILABLE`, `validation_ok=true`, no failed symbols, no stale symbols.
- BEX is preserved as trade/valuation symbol and explicitly resolves to `BE` for signal/earnings evidence.
- Paper safety remains locked: `paper_trade_mode=true`, `live_trading_enabled=false`, `broker_execution_enabled=false`, `order_placement_enabled=false`, `capital_movement_enabled=false`.

### Runtime bugs repaired during this milestone

- Committee evidence previously consumed stale/earlier evidence before current Opportunity Quality existed.
- Current watchlist and portfolio allocations were not guaranteed to refresh in the same cycle.
- Runtime allocation refresh passed the current JSON watchlist into a CSV-only reader; JSON watchlist support was added while preserving CSV compatibility.
- Stock Performance incorrectly displayed held SOXL/TQQQ positions as `current_allocation=0.0` because it did not recognize Portfolio Manager `allocation_before`; the authoritative field is now consumed.
- Candidate NBIS `45%` screening win rate is explicitly prevented from becoming the Enterprise Swing strategy win rate.
- Paper position valuation now updates current prices/P&L without mutating persistent position identity or duplicating BUY events.

### Runtime idempotency evidence

Persistent paper trade history remained exactly two BUY events through repeated report/cycle validation:

- `PAPER-SOXL-2026-08-04-BUY`
- `PAPER-TQQQ-2026-08-04-BUY`

The daily reporting cycle has no paper execution dependency and does not create broker/live execution capability.

## Completed development in the earlier implementation pass

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
- KPI module version advanced to `2.1.5` during that pass; later revisions preserve the same canonical artifact contract.
- Added regression coverage proving `opportunity_quality_report.json` is recognized in the KPI artifact contract and evidence section.

### Canonical market-data refresh status publisher added

The Swing-owned market-data refresh path now publishes `results/market_data_refresh_status.json` and validates current required history before market-data-dependent publication.

Completed:

- Canonical Swing publication of `results/market_data_refresh_status.json`.
- Explicit `SWING-001` ownership and paper/advisory safety flags.
- Atomic publication.
- Explicit blocked status on unavailable/invalid required market evidence.
- Swing-owned symbol-resolution architecture, including BEX → BE signal mapping and newer/leveraged-symbol fallback behavior.
- Same-cycle invocation is now implemented and validated.

### Portfolio allocation producer and current-cycle publication aligned

The authentic producer for `results/portfolio_allocations.json` is `src/swing_trade_bot/portfolio_allocation_engine.py`.

Completed:

- Rank-driven stock-level allocations remain separate from Enterprise strategy-level allocation.
- Removed Strategy B boost/historical-return weighting remains disabled.
- Swing ownership and safety metadata preserved.
- Atomic publication preserved.
- Current JSON watchlist input is supported for same-cycle allocation refresh while CSV compatibility remains.
- Same-cycle regeneration is implemented before downstream Stock Performance.

## Existing unified daily cycle confirmed

`src/swing_trade_bot/swing_daily_cycle.py` is the authoritative unified paper/advisory orchestration path and now implements the current-evidence ordering frozen above.

`run_swing_bot_cycle.py` is the authoritative server launcher candidate. It runs the Swing daily cycle and publishes Enterprise KPI v2.1 only after the cycle succeeds. Do not invent another launcher without evidence that this one is unsuitable.

## Current Enterprise publication status

Receiving-side validation already confirmed the completed Swing → AI CIO filesystem/artifact-path integration:

- `SWING-001` resolves to `/home/tradebot/Trade-Swing-Bot/main`.
- The AI CIO registry recognizes two strategies and accepts Swing externally.
- All currently declared Swing artifacts resolved as `AVAILABLE` during receiving-side validation.
- Enterprise dashboard status was `HEALTHY`.
- Remaining receiving-side warnings observed at that time belonged to Dividend evidence, not Swing.

The runtime-evidence milestone above now provides refreshed, internally consistent Swing values for the next AI CIO/dashboard refresh.

## Implementation tasks

### Task A — Complete producer mapping

Status: **COMPLETE FOR CURRENT DECLARED SWING PUBLICATION SURFACE**

- [x] Inspect external AI CIO handoff.
- [x] Inspect Swing service registration.
- [x] Inspect unified Swing daily cycle.
- [x] Inspect Enterprise KPI v2.1 publisher.
- [x] Confirm authoritative launcher: `run_swing_bot_cycle.py`.
- [x] Locate and wire current `portfolio_allocations.json` producer.
- [x] Locate and wire current `watchlist_report.json` producer.
- [x] Implement and wire current market-data refresh/status before dependent publication.
- [x] Compare current declarations against authentic producer paths during receiving-side integration validation.
- [x] Remove/fix unsupported or stale declarations as part of the completed receiving-side compatibility work rather than fabricating placeholders.

### Task B — Reconcile the external registration contract

Status: **COMPLETE AND RECEIVING-SIDE VALIDATED**

- [x] Add `repository_root=/home/tradebot/Trade-Swing-Bot/main`.
- [x] Convert registered dashboard artifact paths to paths relative to `repository_root`.
- [x] Preserve and extend paper/advisory safety locks, including explicit order-placement disablement.
- [x] Add regression tests for path resolution contract and safety locks.
- [x] AI CIO host accepted the external Swing registration.
- [x] Current declared Swing artifacts resolve under the Swing repository root.

### Task C — Same-cycle unified publication

Status: **COMPLETE AND FROZEN**

- [x] Unified cycle architecture is authoritative.
- [x] Atomic JSON/text publication infrastructure exists.
- [x] Market-data refresh runs before dependent strategy/report publication.
- [x] Watchlist is regenerated as current-cycle evidence.
- [x] Opportunity Quality is regenerated before committee evaluation.
- [x] Committees consume current watchlist + fresh Opportunity Quality.
- [x] Portfolio allocations regenerate from current-cycle inputs.
- [x] Existing paper positions are marked to market without recreating trades.
- [x] Trade-history/performance evidence refreshes before downstream reports.
- [x] Stock Performance consumes current allocation and refreshed paper evidence.
- [x] Weekly/Executive/Monthly reporting follows current Stock Performance.
- [x] Required publication failure produces blocked/nonzero behavior.
- [x] Successful server cycle completed with `15/15 PASS` and exit code `0`.

### Task D — Canonical KPI and allocation-governance alignment

Status: **COMPLETE FOR CURRENT RUNTIME CONTRACT**

- [x] KPI v2.1 publisher exists and writes atomically.
- [x] Allocation provenance is preserved.
- [x] `opportunity_quality_report.json` is the canonical Opportunity Quality evidence path.
- [x] Runtime paper portfolio receives the governed allocation through Enterprise allocation discovery rather than a literal `$4,500` in `swing_daily_cycle.py`.
- [x] Governed `$4,500.00` allocation verified end to end.
- [x] Unknown/unavailable strategy win rate remains `null` when no closed trades exist.
- [x] Candidate watchlist win rate is not promoted to Enterprise strategy performance.
- [x] Allocation is distinct from portfolio value, unrealized P&L, and realized performance.
- [x] Final KPI publication verified: allocated capital `$4,500.00`, portfolio value `$4,525.52`, position count `2`, unrealized P&L `+$25.52`, closed trades `0`, win rate `null`.

### Task E — Required Swing regression QA

Status: **COMPLETE FOR RUNTIME-EVIDENCE MILESTONE**

- [x] Registration repository-root and relative-path contract coverage.
- [x] Registration safety-lock coverage.
- [x] KPI Opportunity Quality artifact-path coverage.
- [x] Market-data ownership/safety/freshness/fallback coverage.
- [x] Portfolio allocation ownership/safety/atomicity coverage.
- [x] Current JSON watchlist allocation-input coverage.
- [x] Current Opportunity Quality reaches Opportunity Committee.
- [x] Current Entry Score is consumed when available; missing evidence is not fabricated.
- [x] Existing paper positions survive report/cycle refresh.
- [x] Daily report cycle does not duplicate persistent BUY transactions.
- [x] Current portfolio mark-to-market/P&L is supported.
- [x] Candidate watchlist win rate cannot become strategy-wide win rate.
- [x] Stock Performance uses Portfolio Manager `allocation_before` as current allocation.
- [x] Governed Enterprise allocation remains externally sourced and is not hard-coded into the daily cycle.
- [x] Paper-only safety flags remain enforced.
- [x] Full suite validated on DigitalOcean: `965 passed, 1 skipped`.

### Task F — Swing-owned systemd deployment

Status: **NEXT SWING-OWNED DEVELOPMENT AFTER AI CIO DISPLAY VERIFICATION**

- [x] Existing launcher verified: `/home/tradebot/Trade-Swing-Bot/main/run_swing_bot_cycle.py`.
- [x] Launcher successfully completes the current publication contract manually.
- [ ] Create/verify a Swing-owned oneshot service using the Swing working directory and `.venv`.
- [ ] Create/verify a separate Swing timer.
- [ ] Do not modify `dividend-bot.service` or `dividend-allocation.service` to execute Swing.
- [ ] Verify service/timer status and journal output.

### Task G — End-to-end AI CIO acceptance and display verification

Status: **FILESYSTEM/ARTIFACT INTEGRATION COMPLETE; CURRENT-VALUE DISPLAY REFRESH PENDING**

- [x] AI CIO registry recognizes `SWING-001` externally.
- [x] Evidence paths resolve beneath `/home/tradebot/Trade-Swing-Bot/main/results/`.
- [x] Receiving-side validation reported all declared Swing artifacts available.
- [x] Governed allocation remained `$4,500.00`.
- [x] Enterprise dashboard status reported `HEALTHY` during integration validation.
- [ ] Refresh AI CIO receiving-side dashboards after the 2026-08-13 current-runtime milestone.
- [ ] Verify displayed Opportunity Quality is sourced from current `15.458` evidence rather than an old `1.0` value.
- [ ] Verify displayed positions/holdings reflect `2` current paper positions.
- [ ] Verify displayed portfolio value/P&L reflects current Swing paper evidence.
- [ ] Verify displayed strategy win rate is unavailable/null with zero closed trades rather than the candidate NBIS `45%` screening statistic.
- [ ] Verify remaining warnings after refresh belong only to their true owning strategy/repository.

## Key commits from the runtime-evidence alignment work

- `fc6b207` — fix freeze-markdown renderer import compatibility.
- `0b9f47d` — skip optional legacy Enterprise V1 SDK suite when SDK is absent.
- `b657426` / `e2777b0` — align Enterprise KPI tests with supported allocation evidence schema.
- `0a3433c` — align report-orchestration tests with current evidence order.
- `79b841b` — read current JSON watchlist during runtime allocation refresh.
- `b1f17b5` — regression coverage for JSON watchlist allocation input.
- `eff658f` — use Portfolio Manager `allocation_before` as Stock Performance current allocation.
- `8a49ba0` — regression coverage for current allocation authority.

## Evidence package at runtime-evidence freeze

- Full tests: `965 passed, 1 skipped`, exit code `0`.
- Manual `python run_swing_bot_cycle.py`: `COMPLETE`, `15/15 PASS`, exit code `0`.
- Manual `python publish_enterprise_strategy_kpis_v21.py`: successful publication.
- Opportunity Quality: `15.458` for NBIS.
- Committee Opportunity Quality: `15.458`, source available, threshold failure preserved.
- Entry Score: `0.0`, no fabrication.
- Positions: SOXL and TQQQ, count `2`.
- Portfolio value: `$4,525.52`.
- Unrealized P&L: `+$25.52`.
- Closed trades: `0`.
- Strategy win rate: `null` / insufficient closed-trade evidence.
- Market data: `AVAILABLE`, valid, no failed/stale symbols.
- BEX signal resolution: `BEX` trade/valuation → `BE` signal/earnings.
- Enterprise allocation: `$4,500.00`, source `AI_CIO_ENTERPRISE_EVIDENCE`.
- No Dividend Bot production files were modified by this Swing development milestone.

## Continuation instruction for a new chat

If this work moves to a new Trade Swing Bot chat:

1. Read this tracker first.
2. Treat the 2026-08-13 Runtime Evidence Refresh and Authority Alignment milestone as frozen unless a regression is demonstrated.
3. Do not change Opportunity Quality Version 1.2 weights or fabricate missing evidence.
4. Do not change the AI CIO governed `$4,500.00` Swing allocation inside Swing.
5. Preserve the frozen same-cycle dependency order.
6. Preserve the paper-only safety boundary and repository containment boundary.
7. Resume with Task G current-value display verification; after that, proceed to Task F Swing-owned systemd deployment unless the user reprioritizes.
8. Update this tracker whenever a task is completed, a contract decision changes, or a new blocker is discovered.

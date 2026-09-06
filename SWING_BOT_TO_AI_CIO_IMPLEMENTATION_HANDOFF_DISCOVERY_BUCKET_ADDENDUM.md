# Swing Bot to AI CIO Handoff Addendum — Enterprise Discovery Bucket

Last updated: 2026-08-21

## Product decision

The Enterprise AI CIO owns broad market discovery intelligence and may publish a weekly bucket of underlying stocks/sectors classified as HOT, RISING, EMERGING, COOLING, or DECLINING.

Swing remains the sole authority for Swing lifecycle state. AI CIO nomination never directly creates WATCHLIST, LOW, MEDIUM, HIGH, allocation, entry, exit, BUY, SELL, or paper-position state.

The intended authority chain is:

AI CIO discovery bucket -> Swing explicit leveraged mapping -> Swing DISCOVERY candidate -> existing Discovery Engine evidence/confluence lifecycle -> Opportunity Quality -> Entry Score -> paper lifecycle.

Permanent architecture statement:

**AI CIO discovers leadership. SWING-001 evaluates the trade.**

## Implemented Swing-side intake

Authoritative base consumer:

- `main/src/swing_trade_bot/enterprise_discovery_bucket.py`

Discovery Leadership v1 context adapter:

- `main/src/swing_trade_bot/enterprise_discovery_leadership_context.py`

New mapping configuration:

- `main/configs/swing_discovery_leveraged_mapping.json`

Regression suites:

- `main/tests/test_enterprise_discovery_bucket.py`
- `main/tests/test_enterprise_discovery_leadership_context.py`
- `main/tests/test_run_swing_bot_cycle.py`

Launcher integration:

- `main/run_swing_bot_cycle.py` materializes Enterprise discovery runtime inputs before market-data refresh and the normal Swing cycle.
- The launcher now also snapshots optional AI CIO Discovery Leadership evidence as read-only Swing context immediately after the base discovery intake.

Daily-cycle input configuration:

- `results/discovery_candidates_runtime.csv`
- `results/discovery_mentions_runtime.csv`

The base intake publishes diagnostic evidence to:

- `results/enterprise_discovery_intake_report.json`

Discovery Leadership context is preserved separately in:

- `results/enterprise_discovery_leadership_context.json`

## Read-only AI CIO contract

Default AI CIO repository root:

- `/home/tradebot/Trade-Dividend-Bot`
- override with `AI_CIO_REPOSITORY`

Expected AI CIO artifact:

- `results/enterprise_swing_discovery_bucket.json`

Expected bucket schema version: `1.0`.

Each candidate requires:

- `underlying_symbol`
- `discovery_status` in HOT/RISING/EMERGING/COOLING/DECLINING
- `evidence_sources` remains authoritative when supplied

Optional base evidence may include:

- themes
- source-level evidence entries
- source
- mentioned_on
- earnings-growth relevance
- analyst-upgrade relevance

Only HOT, RISING, and EMERGING can create a new Swing candidate. New candidates require an explicit Swing-owned underlying-to-leveraged mapping and always enter at `DISCOVERY` with zero paper history.

COOLING and DECLINING do not create new candidates. Existing Swing candidates may consume bucket themes/evidence but retain their Swing-owned lifecycle/performance state.

If the AI CIO bucket does not yet exist, Swing safely materializes the existing local candidate and mention inputs unchanged using `SWING_LOCAL_FALLBACK`.

Malformed Enterprise source evidence fails closed.

## Discovery Leadership v1 consumer integration

AI CIO Discovery Leadership v1 remains additive to the existing SWING-001 schema `1.0` contract. Legacy buckets without leadership fields remain valid and continue through the original intake unchanged.

When present, Swing preserves the following AI CIO-owned fields as upstream context:

- `discovery_leadership_score`
- `discovery_leadership_classification`
- `relative_leadership`
- `sector_leadership`
- `industry_leadership`
- `theme_leadership`
- `discovery_reasons`
- `discovery_warnings`

Nested `relative_leadership` evidence, including benchmark identity, evidence status, leadership score/classification, evaluated/leader horizons, persistence, history sources, warnings, and `1m`/`3m`/`6m`/`ytd` horizon payloads, is preserved without recalculation.

Available horizon evidence may include:

- `stock_return_pct`
- `benchmark_return_pct`
- `relative_outperformance_pct`
- `relative_multiple`
- `leadership_classification`
- `trapper_2x_spy_evidence`
- `period_start`
- `period_end`
- `freshness_days`

Swing does not normalize missing leadership evidence to zero. Optional fields that are absent upstream remain absent in the context artifact.

The Discovery Leadership context adapter does not add fields to durable `CandidateState`. This deliberately keeps rapidly changing upstream discovery evidence separate from Swing-owned lifecycle/performance state.

## Discovery Leadership ownership boundary

AI CIO owns and calculates Discovery Leadership.

Swing MUST NOT:

- recalculate AI CIO leadership scores
- change AI CIO leadership thresholds
- reinterpret the Trapper 2x-SPY rule
- recreate sector or industry leadership
- modify AI CIO market history
- treat STRONG/LEADER/EXCEPTIONAL_LEADER as automatic BUY authority

The context artifact explicitly reports:

- `leadership_owner = AI_CIO`
- `leadership_recalculated_by_swing = false`
- `leadership_used_as_automatic_buy_signal = false`
- `opportunity_quality_weights_changed = false`
- `entry_score_changed = false`

Discovery Leadership is not an eighth Opportunity Quality component. Opportunity Quality Version 1.2 remains frozen at its existing seven components and weights. Leadership context may be inspected by downstream Swing setup/evaluation logic without changing those frozen calculations unless a separate future architecture decision explicitly reopens OQ.

Swing continues to own:

- SMA20 / SMA50 / SMA200 setup conditions
- pullback and parabolic-move analysis
- previous-high reclaim
- base / consolidation detection
- pivot and breakout logic
- volume confirmation
- Opportunity Quality
- Entry Score
- entry eligibility
- exit logic
- position sizing
- paper-trade execution

## Explicit mapping policy

No leveraged relationship is inferred from ticker spelling.

Current mapping configuration includes:

- AMZN -> AMZU
- GOOGL -> GGLL
- NFLX -> NFLU
- NVDA -> NVDX
- PLTR -> PLTU
- AVGO -> AVL

Mappings remain Swing-owned and can be expanded only with verified products.

## Safety invariants

Preserved:

- SWING-001
- paper-only operation
- AI CIO governed strategy allocation
- no broker execution
- no order placement
- no capital movement
- no Robinhood integration
- no fabricated lifecycle transitions
- no Opportunity Quality Version 1.2 weight changes
- no Entry Score changes

## Validation status

Discovery Leadership consumer implementation commits on `feature/swing-phase2-enterprise-market-data`:

- `d93916e` — preserve AI CIO Discovery Leadership as read-only Swing context
- `1fa4c71` — wire the context refresh into the authoritative Swing launcher
- `6604dcf` — preserve launcher ordering in regression tests
- `645a03b` — add backward-compatibility, preservation, Trapper-context, and no-BUY regression coverage

Focused DigitalOcean validation is required before deployment acceptance:

```bash
cd /home/tradebot/Trade-Swing-Bot/main
source .venv/bin/activate

PYTHONPATH="$PWD:$PWD/src" python -m py_compile \
  src/swing_trade_bot/enterprise_discovery_bucket.py \
  src/swing_trade_bot/enterprise_discovery_leadership_context.py \
  run_swing_bot_cycle.py

PYTHONPATH="$PWD:$PWD/src" python -m pytest \
  tests/test_enterprise_discovery_bucket.py \
  tests/test_enterprise_discovery_leadership_context.py \
  tests/test_run_swing_bot_cycle.py \
  -q --cache-clear
```

Then run the leadership context refresh against the real AI CIO producer without running execution logic:

```bash
PYTHONPATH="$PWD:$PWD/src" python -m swing_trade_bot.enterprise_discovery_leadership_context
```

Inspect:

- `results/enterprise_discovery_leadership_context.json`

Confirm that AI CIO values such as AMAT/SJM/ULTA/INTS/FSBW, when present in the producer artifact, survive unchanged; missing leadership evidence remains missing; upstream `discovery_warnings` survive; and no BUY/SELL/order authority appears in the context artifact.

After focused validation, run the full Swing repository regression suite before declaring the consumer integration frozen.

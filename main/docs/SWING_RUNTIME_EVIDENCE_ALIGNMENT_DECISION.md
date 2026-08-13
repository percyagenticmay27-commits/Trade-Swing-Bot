# Swing Runtime Evidence Refresh and Authority Alignment

Last updated: 2026-08-12

## Purpose

This decision record freezes the completed Swing -> Enterprise AI CIO filesystem/artifact-path integration and documents the next runtime evidence correction inside Trade-Swing-Bot only.

The goal is to prevent a successful current Swing cycle from combining freshly generated reports with stale watchlist, allocation, committee, or paper-ledger evidence.

## Frozen boundaries

- Strategy identity remains `SWING-001`.
- AI CIO owns Enterprise strategy allocation governance.
- Swing reads the governed allocation through the existing Enterprise allocation discovery/provenance path.
- No `$4,500` production literal is introduced by this work.
- Swing never writes into Trade-Dividend-Bot.
- `paper_trade_mode=true` remains permanent.
- `live_trading_enabled=false`.
- `broker_execution_enabled=false`.
- `order_placement_enabled=false`.
- `capital_movement_enabled=false`.
- No Robinhood execution, account access, authentication, or order placement is introduced.
- The completed external repository-root/artifact-path compatibility contract is unchanged.

## Verified pre-fix evidence problems

The DigitalOcean runtime showed a current Enterprise KPI, current market-data status, current Opportunity Quality report, current Stock Performance report, and current committee trace while these inputs remained older:

- `results/watchlist_report.json` — 2026-07-30.
- `results/portfolio_allocations.json` — 2026-07-30.
- `results/paper_ledger/open_positions.json` — generated 2026-08-05.
- `results/paper_ledger/paper_portfolio_summary.json` — generated 2026-08-05.

The legitimate persistent paper positions were:

- SOXL — cost basis $1,125.
- TQQQ — cost basis $675.

The old committee ordering generated committee runtime evidence before the same cycle rebuilt Opportunity Quality. As a result, the Opportunity Committee reported `score_available=false` even though the cycle subsequently produced NBIS Opportunity Quality `15.458`.

The stale watchlist also contained NBIS candidate-lifecycle `win_rate=45.0`. That value is not authoritative strategy-wide Swing performance and must never become Enterprise `win_rate_percent` without completed-paper-trade evidence.

## Opportunity Quality decision

`opportunity_quality_engine.py` Version 1.2 calculations remain unchanged.

Frozen weights remain:

- Fundamental Analysis: 20%.
- Market Intelligence: 20%.
- Conviction: 20%.
- Momentum: 15%.
- Technical Analysis: 15%.
- Market Regime Support: 5%.
- Portfolio Risk Adjustment: 5%.

Entry Score remains independent/display-only.

Missing evidence remains zero.

Therefore NBIS `15.458` is a valid score when the only available component is Fundamental Analysis `77.29`: `77.29 * 0.20 = 15.458`.

No score is increased merely to populate the dashboard.

## Circular dependency removed

Before:

`committee runtime -> Opportunity Quality input selection -> Opportunity Quality -> reports`

This was circular because committees are supposed to consume Opportunity Quality.

After:

`current ranked watchlist -> Opportunity Quality inputs -> Opportunity Quality -> committee runtime -> committee trace`

The ranked watchlist now owns candidate selection for Opportunity Quality input assembly. Stale committee evidence can no longer choose the current Opportunity Quality candidate.

## Current-cycle producer ordering

The unified cycle now follows this internal dependency order after the Swing-owned market refresh performed by `run_swing_bot_cycle.py`:

1. Refresh watchlist from configured candidate state, discovery mentions, and financial-health evidence.
2. Rebuild Opportunity Quality inputs from the current ranked watchlist.
3. Rebuild Opportunity Quality using the frozen Version 1.2 engine.
4. Rebuild committee runtime evidence from current watchlist plus fresh Opportunity Quality.
5. Rebuild the append-only committee decision trace.
6. Rebuild stock-level portfolio allocations through the existing allocation engine.
7. Mark existing persistent paper positions to current completed market data through the existing Paper Portfolio Manager.
8. Adapt the valued paper positions into the existing Portfolio Manager input schema and rebuild current rebalance evidence.
9. Rebuild normalized trade history and closed-position evidence from the persistent paper trade ledger.
10. Rebuild authoritative paper performance analytics.
11. Rebuild Stock Performance from current allocation and portfolio-manager evidence.
12. Rebuild Weekly Stock, Executive Dashboard, and Monthly Command Center reports.
13. Publish Enterprise KPI evidence only after the Swing cycle succeeds.
14. AI CIO remains a read-only receiver of Swing artifacts.

## Watchlist authority and freshness

The existing `discovery_engine.py` remains the authoritative watchlist writer.

The daily cycle uses configured candidate state, discovery mentions, financial health, and the cycle date to reevaluate the watchlist. The JSON receives current-cycle metadata:

- `strategy_id=SWING-001`.
- `generated_at_utc`.
- `as_of_date`.
- `freshness_status=CURRENT_CYCLE`.
- source artifact paths.
- `screening_performance_scope=CANDIDATE_LIFECYCLE_INPUT_NOT_STRATEGY_PERFORMANCE`.

This explicitly prevents candidate screening statistics such as the historical NBIS `45%` value from being misrepresented as strategy-wide performance.

If required configured watchlist inputs are unavailable, the cycle fails closed instead of silently reusing an old watchlist.

## Committee authority

`swing_committee_runtime_evidence.py` now reads Opportunity Quality from the freshly published `opportunity_quality_report.json`.

For example, when the current score is `15.458`, the Opportunity Committee must receive `15.458` and fail the 70-point threshold truthfully. It may not report the score as unavailable merely because an older pre-quality artifact lacks the value.

Entry Score remains truthful. The committee uses current Opportunity Quality report evidence first and current Opportunity Quality input evidence only for entry/thesis fields when needed. Missing Entry Score remains missing/HOLD; it is never invented.

Portfolio Committee no longer requires a preexisting allocation artifact to decide eligibility. This removes the reverse dependency between committee approval and allocation generation. A candidate that clears Opportunity and Entry becomes `ELIGIBLE_FOR_ALLOCATION`; the allocation engine then determines the actual stock-level allocation.

## Portfolio allocation authority

`portfolio_allocation_engine.py` remains the stock-level allocation engine.

The daily cycle rebuilds `portfolio_allocations.json` and `.csv` from current confidence, current watchlist, and strategy recommendation evidence.

No stock allocation is hard-coded because SOXL or TQQQ already exists in the paper ledger. Unranked evidence remains unranked according to the existing engine behavior.

Stock-level allocations are independent from Enterprise strategy-level capital governance.

## Paper position authority

`open_positions.json` remains persistent execution state and is not recreated by this runtime refresh.

The daily cycle does not call `paper_execution_engine` and therefore cannot generate duplicate August 4 BUY events merely because the cycle reruns.

`paper_portfolio_manager.py` marks persistent positions to current completed local market bars and atomically publishes:

- `paper_portfolio_summary.json`.
- `paper_portfolio_positions.json`.

The governed account capital is supplied through Enterprise allocation discovery, not a Swing constant. Allocation provenance is attached to the paper summary.

The current valued position JSON is adapted into `current_portfolio_positions.csv` only so the existing `portfolio_manager.py` can produce fresh rebalance/current-allocation evidence. This adapter does not write or mutate `open_positions.json`.

## Trade history and win-rate authority

`trade_history_manager.py` rebuilds managed history, FIFO closed trades, and the trade-history summary from persistent `trade_history.json`.

`performance_analytics_engine.py` is authoritative for strategy performance.

If there are no decided closed paper trades, `win_rate_percent` remains `null` and a warning is published. Candidate/watchlist win rate is never promoted into Enterprise strategy win rate.

## Enterprise KPI authority correction

Enterprise KPI v2.1 now accepts the Paper Portfolio Manager's split-adjusted mark-to-market valuation source and uses the current paper portfolio for:

- portfolio value.
- cash balance.
- invested capital.
- positions market value.
- unrealized P/L.
- portfolio return.
- position count.
- detailed open positions.

Opportunity Quality is also extracted from current report rows when the report does not expose a top-level score. Thus a genuine current NBIS `15.458` can flow to Enterprise KPI rather than appearing as unavailable.

Strategy-wide win rate still comes only from authoritative paper performance analytics.

## Regression coverage added

Tests cover:

- ranked-watchlist-owned Opportunity Quality selection.
- stale committee evidence cannot override current candidate selection.
- current Opportunity Quality reaches Opportunity Committee.
- current Entry Score reaches Entry Committee when available.
- missing Entry Score remains truthful.
- fresh Opportunity Quality cannot be overridden by old input evidence.
- daily report producer ordering puts Opportunity Quality before committees.
- old current-cycle intermediates are rebuilt rather than reused merely because files exist.
- split-adjusted current paper portfolio evidence reaches Enterprise KPI.
- row-level current Opportunity Quality reaches Enterprise KPI.
- watchlist 45% cannot become Enterprise strategy win rate.
- current marked-to-market holdings feed the existing Portfolio Manager adapter.
- the holdings adapter cannot mutate persistent `open_positions.json`.
- daily cycle has no paper execution or Robinhood dependency.
- Enterprise allocation is discovered externally and no `$4,500` literal is introduced into the daily cycle.

## Remaining validation

This development must be pulled to DigitalOcean and validated against the real runtime evidence before being declared frozen.

Required server validation includes targeted tests, full Swing tests, a controlled `run_swing_bot_cycle.py`, direct Enterprise KPI publication, current artifact timestamps/provenance, current SOXL/TQQQ mark-to-market values, authoritative win-rate status, market-data freshness, BEX resolution evidence, and all paper-safety locks.

Do not modify Trade-Dividend-Bot as part of this validation.

# Swing Market Data Resilience Decision

Last updated: 2026-08-12

## Purpose

Record the permanent Swing-owned market-data decisions made after the DigitalOcean daily cycle correctly blocked on stale June 2026 history and Yahoo HTTP 429 responses.

## Observed production blocker

DigitalOcean `results/market_data_refresh_status.json` reported all configured historical symbols unable to refresh. Yahoo CSV and Yahoo Chart returned HTTP 429, Stooq returned HTTP 404, and the local CSV set ended on 2026-06-22. The cycle remained paper-safe and correctly refused market-data-dependent publication.

The old validation rule also required 252 rows for every security. That was inappropriate for newer funds that have not existed for 252 trading sessions.

## Architecture decisions

1. Swing remains the owner of Swing market data. No Dividend production code is imported and Swing does not write into the Dividend/AI CIO repository.
2. Trade identity and technical-signal identity are separate concepts.
3. The traded/valuation symbol is never replaced by an underlying stock price.
4. Explicit verified single-stock leveraged mappings may use the underlying only for technical-signal and earnings evidence.
5. No ticker mapping is guessed from spelling.
6. Basket/index products without an approved proxy remain ETF-native for historical evidence.
7. Stale local history is labeled stale and may be retained for diagnostics, but it does not satisfy the daily publication gate when live refresh fails.
8. Market-data writes are atomic.
9. No Robinhood authentication, account access, order placement, capital movement, or execution capability is introduced.
10. A future read-only Robinhood/Codex provider may be added only after its exact source/API contract is supplied and separately reviewed. It is currently disabled.

## Verified symbol mappings

| Trade symbol | Valuation symbol | Technical signal symbol | Earnings symbol | Basis |
|---|---|---|---|---|
| BEX | BEX | BE | BE | Tradr 2X Long BE Daily ETF explicitly targets Bloom Energy (BE) |
| IRE | IRE | IREN | IREN | Defiance Daily Target 2X Long IREN ETF explicitly targets IREN |
| IONL | IONL | IONQ | IONQ | GraniteShares 2x Long IONQ Daily ETF explicitly targets IONQ |
| DRAM | DRAM | not configured | not configured | diversified Roundhill Memory ETF; no single-stock proxy is authorized |

BEX, IRE and IONL therefore keep their ETF symbol for paper holdings and valuation while their verified underlying can supply technical/earnings evidence. DRAM fails closed for an underlying signal request and remains ETF-native in the daily historical gate.

## Provider/cache order now implemented

For historical OHLCV acquisition:

1. fresh local Swing CSV cache;
2. Yahoo historical CSV;
3. Yahoo Chart API;
4. Stooq U.S. daily download endpoint;
5. optional explicitly supplied historical CSV import;
6. stale local Swing CSV for diagnostic fallback only;
7. unavailable.

HTTP 429 receives bounded retry/backoff. Public provider requests identify themselves with a read-only User-Agent. Stooq retains its verified U.S. `symbol.us` download form.

## Freshness metadata

`DownloadSummary` now carries:

- `source`
- `data_source`
- `is_stale`
- `retrieved_at_utc`
- provider error text when applicable

Supported source-state labels include:

- `CACHE_FRESH`
- `LIVE_PROVIDER`
- `HISTORICAL_CSV_FALLBACK`
- `CACHE_STALE_FALLBACK`
- `UNAVAILABLE`

A stale fallback keeps provider errors, causing the daily publication gate to remain blocked rather than treating old evidence as current.

## Listing-age-aware validation

Mature symbols keep the 252-bar requirement.

For a security with a verified inception date, required history is capped by an estimate of the trading sessions that could actually have existed since inception, with a small exchange-holiday allowance. The requirement never falls below 50 completed daily observations, preserving the EMA50 evidence floor.

This prevents a new fund from being rejected solely because pre-inception history does not exist while still rejecting materially stale history.

## Daily Swing market-data gate

The daily gate now requests mapped technical-evidence symbols rather than demanding ETF-native history for every explicitly mapped single-stock leveraged product.

For the current strategy set this means the required technical evidence includes BE instead of BEX, IREN instead of IRE, and IONQ instead of IONL. Unmapped symbols remain self-sourced. SPY and QQQ remain benchmark requirements.

`results/market_data_refresh_status.json` now records symbol mappings, stale symbols, warnings, provider metadata, paper-only safety locks, and `robinhood_market_data_enabled=false`.

## Files changed in this pass

- `src/swing_trade_bot/market_symbol_mapping.py`
- `src/swing_trade_bot/data_tools.py`
- `src/swing_trade_bot/data_download.py`
- `src/swing_trade_bot/swing_market_data_refresh.py`
- `tests/test_market_symbol_mapping.py`
- `tests/test_listing_age_validation.py`
- `tests/test_market_data_resilience.py`
- `tests/test_swing_market_data_refresh.py`

## DigitalOcean validation still required

Before the next real Swing cycle:

1. pull `feature/swing-phase2-enterprise-market-data`;
2. compile the four changed production modules;
3. run the four focused market-data test files plus existing `test_data_download.py` and `test_data_tools.py`;
4. run `tests/test_run_swing_bot_cycle.py`;
5. run the Swing market refresh directly and inspect `results/market_data_refresh_status.json`;
6. only if the status is `AVAILABLE`, run `run_swing_bot_cycle.py`;
7. verify regenerated Enterprise KPI/dashboard timestamps before refreshing the AI CIO receiving side.

## Continuation rule

If this work moves to another chat, read this file together with `SWING_AI_CIO_IMPLEMENTATION_DECISION_TASK_TRACKER.md` before changing market data. Do not reintroduce a Dividend-hosted Swing market-data dependency, do not substitute underlying prices for traded ETF valuation, and do not bypass stale/unavailable evidence safety gates.

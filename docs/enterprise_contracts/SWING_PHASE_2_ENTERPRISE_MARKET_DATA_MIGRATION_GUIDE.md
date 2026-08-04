# Swing Phase 2 Enterprise Market Data Migration Guide

## Purpose

This guide defines the exact Phase 2 migration for `SWING-001` after completion of the Dividend AI CIO Enterprise Market Data Provider Version 1.0.

The migration replaces stale local CSV files as the Swing Bot's primary market-data source without changing strategy calculations, committee logic, allocation logic, portfolio rules, lifecycle behavior, or paper-only protections.

The Swing repository must preserve its stale-data rejection and must not silently fall back to stale `data/SOXL.csv`, `data/TQQQ.csv`, or another outdated local market-data file.

## 1. Provider contract file and path

Machine-readable contract:

```text
/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_contract.json
```

Human-readable host contract:

```text
/home/tradebot/Trade-Dividend-Bot/docs/ENTERPRISE_MARKET_DATA_PROVIDER_V1.md
```

Swing documentation copy:

```text
docs/enterprise_contracts/ENTERPRISE_MARKET_DATA_PROVIDER_V1.md
```

Provider operations:

```text
get_quote(symbol)
get_history(symbol, period, interval)
get_latest_close(symbol)
get_previous_close(symbol)
get_volume(symbol)
get_split_history(symbol)
get_dividend_history(symbol)
```

Swing must not import Dividend production modules or duplicate provider-selection logic.

## 2. Service and command used to request quote/history data

Systemd service:

```text
enterprise-market-data-refresh.service
```

Start and inspect:

```bash
sudo systemctl start enterprise-market-data-refresh.service
sudo systemctl status enterprise-market-data-refresh.service --no-pager
sudo journalctl -u enterprise-market-data-refresh.service --no-pager -n 200
```

Direct `SWING-001` refresh:

```bash
/home/tradebot/Trade-Dividend-Bot/.venv/bin/python \
  /home/tradebot/Trade-Dividend-Bot/refresh_enterprise_market_data.py \
  --strategy-id SWING-001 \
  --required-symbol SOXL \
  --required-symbol TQQQ \
  --cache-dir /var/lib/enterprise-market-data-cache
```

Cost-aware precedence:

```text
YFINANCE -> STOOQ -> fresh LOCAL_CACHE -> ROBINHOOD_MCP -> SAFE_FAILURE
```

Normal successful public-provider refreshes consume no Codex usage.

## 3. JSON request and response examples

Recommended quote request:

```json
{
  "schema_version": "1.0",
  "operation": "get_quote",
  "strategy_id": "SWING-001",
  "symbol": "SOXL",
  "required": true
}
```

Recommended history request:

```json
{
  "schema_version": "1.0",
  "operation": "get_history",
  "strategy_id": "SWING-001",
  "symbol": "SOXL",
  "period": "1mo",
  "interval": "1d",
  "required": true
}
```

Normalized quote response:

```json
{
  "symbol": "SOXL",
  "price": 140.15,
  "quote_timestamp": "2026-08-04T19:59:04+00:00",
  "trading_date": "2026-08-04",
  "provider": "YFINANCE",
  "source_type": "LIVE_QUOTE",
  "stale": false,
  "confidence": 0.9,
  "warnings": [],
  "cache_used": false
}
```

Normalized history response:

```json
{
  "symbol": "SOXL",
  "interval": "1d",
  "period": "1mo",
  "provider": "YFINANCE",
  "generated_at": "2026-08-04T19:59:04+00:00",
  "latest_bar_date": "2026-08-04",
  "stale": false,
  "corporate_action_adjusted": false,
  "split_history": [],
  "dividend_history": [],
  "cache_used": false,
  "warnings": [],
  "bars": [
    {
      "date": "2026-08-04",
      "open": 137.5,
      "high": 141.2,
      "low": 136.8,
      "close": 140.15,
      "adjusted_close": 140.15,
      "volume": 12345678
    }
  ]
}
```

Published strategy status includes both `SOXL` and `TQQQ`, with quote and history records for each.

## 4. Evidence output paths

```text
/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_status.json
/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_provider_health.json
/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_refresh.csv
/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_contract.json
```

Persistent cache:

```text
/var/lib/enterprise-market-data-cache
```

Transient Robinhood handoff directory:

```text
/run/enterprise-market-data-handoff
```

Swing must consume normalized AI CIO output, not Robinhood handoff files directly.

## 5. Codex/Robinhood bridge and systemd integration

Service name:

```text
enterprise-market-data-refresh.service
```

Conditional fallback evaluator:

```text
/home/tradebot/Trade-Dividend-Bot/refresh_robinhood_fallback_handoffs.py
```

Root-owned read-only handoff entry point:

```text
/home/tradebot/Trade-Dividend-Bot/root_codex_market_data_handoff.py
```

Codex executable:

```text
/usr/local/bin/codex
```

The bridge is invoked only for unresolved quote/history operations. Swing must not invoke Codex, Robinhood MCP, or the root handoff directly.

## 6. Freshness rules

Version 1.0 defaults:

```text
Quote maximum age: 900 seconds
Daily history maximum age: 5 calendar days
```

Rules:

- Stale quotes are rejected.
- Stale history is rejected.
- Stale cache is rejected.
- Conflicting duplicate bars are rejected.
- Required historical bars need valid date, OHLC, and volume.
- Missing required quote or history blocks only the requesting strategy.
- Missing optional-symbol data produces a warning.
- Existing Swing stale-data protection remains active as a second boundary.

## 7. Failure and status values

Strategy statuses:

```text
READY
WARNING
BLOCKED
```

Per-symbol statuses:

```text
FRESH
WARNING
BLOCKED
```

Behavior:

- `READY`: continue the Swing cycle.
- `WARNING`: continue using valid required-symbol data and surface optional warnings.
- `BLOCKED`: stop market-data-dependent publication and valuation steps for `SWING-001` only.

Never:

- substitute entry price for a missing current price;
- report cost basis as market value because quote data is missing;
- report missing unrealized P&L as zero;
- publish stale KPI, executive-summary, dashboard, or email values as fresh.

## 8. DigitalOcean deployment paths

Dividend AI CIO root:

```text
/home/tradebot/Trade-Dividend-Bot
```

Python:

```text
/home/tradebot/Trade-Dividend-Bot/.venv/bin/python
```

Results:

```text
/home/tradebot/Trade-Dividend-Bot/results
```

Installed systemd unit:

```text
/etc/systemd/system/enterprise-market-data-refresh.service
```

Recommended Swing environment variables:

```text
ENTERPRISE_MARKET_DATA_STATUS_PATH=/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_status.json
ENTERPRISE_MARKET_DATA_CONTRACT_PATH=/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_contract.json
ENTERPRISE_MARKET_DATA_HEALTH_PATH=/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_provider_health.json
```

Use read-only access. Do not loosen permissions on the entire Dividend repository and do not copy OAuth credentials.

## 9. Tests and final pass summary

Final focused Phase 1 result on DigitalOcean:

```text
33 passed
```

Validated production result:

```text
strategy_id: SWING-001
status: READY
```

Both required symbols returned:

```text
SOXL: FRESH quote and history
TQQQ: FRESH quote and history
quote_stale: false
history_stale: false
latest_bar_date: 2026-08-04
history bar count: 122
```

The successful validation provider was `YFINANCE`. Robinhood remained a conditional fallback.

## 10. SWING-001-specific integration instructions

### Permanent rules

- Preserve the existing `$4,500` `SWING-001` allocation.
- Do not modify Dividend allocation state.
- Do not change strategy, Opportunity Quality, committee, discovery, watchlist, allocation, entry, exit, lifecycle, or paper-only calculations.
- Do not import Dividend production modules.
- Do not duplicate provider selection in Swing.
- Do not remove stale-data rejection.

### Step 1: Add a Swing-owned adapter

Recommended module:

```text
src/swing_trade_bot/enterprise_market_data_client.py
```

Responsibilities:

- Read the host contract and strategy status.
- Validate schema version `1.0`.
- Select requested symbol records.
- Return normalized quote/history data.
- Raise a Swing-owned `MarketDataUnavailable` on missing, stale, malformed, or blocked data.

The adapter must remain provider-neutral and must not perform portfolio calculations.

### Step 2: Replace primary CSV reads

Trace direct primary reads of:

```text
data/SOXL.csv
data/TQQQ.csv
data/{symbol}.csv
```

Replace the primary source for:

1. Paper Portfolio Manager valuation
2. Current prices
3. Historical bars
4. Technical indicators
5. Performance analytics
6. Executive summary CSV
7. Enterprise KPI evidence
8. Daily email

Local CSVs may remain only as explicitly labeled fixtures, samples, or archives—not a silent production fallback.

### Step 3: Portfolio valuation

For each open position:

- Use fresh normalized `price` as `current_price`.
- Preserve existing market-value and unrealized-P&L formulas.
- Preserve cost basis and entry price.
- Store provider-neutral timestamp metadata.
- Block affected publication when required data is unavailable.

### Step 4: Historical analytics

Use normalized `bars` for indicators, momentum, performance, trailing calculations, and comparisons. Validate non-empty ordered bars, required OHLCV fields, acceptable latest-bar date, and `stale == false`.

### Step 5: Runtime order

```text
1. Validate host contract Version 1.0
2. Require SWING-001 READY or permitted WARNING
3. Load SOXL and TQQQ quote/history
4. Run portfolio valuation
5. Run existing technical/performance analytics
6. Generate executive summary
7. Publish Enterprise KPI evidence
8. Generate daily email
```

When `BLOCKED`, stop steps 4-8 for `SWING-001` and publish a clear blocked-state report.

### Step 6: Required Swing regression tests

Add tests for:

- Version 1.0 accepted; unknown version rejected
- SOXL and TQQQ records loaded
- Fresh quote/history accepted; stale rejected
- Missing required quote/history blocks `SWING-001`
- Optional failures warn
- Entry price never replaces missing current price
- Market value and unrealized P&L use fresh quote
- Historical bars feed existing indicators unchanged
- Executive summary, KPI evidence, dashboard input, and email use fresh values
- Provider identity does not alter calculations
- No Dividend production imports
- No Robinhood/Codex calls from Swing
- `$4,500` allocation unchanged
- Existing stale-data protection preserved

### Acceptance criteria

Phase 2 is complete only when local CSVs are no longer the primary production source; SOXL/TQQQ valuation and analytics use fresh AI CIO output; stale or missing required data blocks only `SWING-001`; downstream summaries and emails use refreshed values; all existing calculations remain unchanged; and all Phase 2 tests pass.

## Explicit non-goals

Do not add new strategy logic, allocation logic, entry/exit rules, broker execution, live-order behavior, AI committees, dashboard redesign, or Dividend calculations.

## Source of truth

This is the Swing repository's documentation copy. The authoritative guide is maintained in:

```text
Trade-Dividend-Bot/docs/SWING_PHASE_2_ENTERPRISE_MARKET_DATA_MIGRATION_GUIDE.md
```

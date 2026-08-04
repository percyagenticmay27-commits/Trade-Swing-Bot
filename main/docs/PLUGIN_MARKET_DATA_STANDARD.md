# Enterprise Strategy Plugin Market Data Standard

## Purpose

Every external AI-CIO strategy plugin must own, refresh, validate, and publish its own market data. The AI CIO may discover evidence and display health, but it must not silently supply or mutate strategy market data.

## Required architecture

Each strategy repository should implement these boundaries:

1. `MarketDataProvider` interface with no publication side effects.
2. Ordered `MarketDataProviderChain`.
3. Normalization into a stable daily OHLCV model.
4. Validation before publication.
5. Atomic CSV publication.
6. Prior-valid-file fallback.
7. Freshness evidence and blocking rules.
8. Strategy calculations that read only validated local artifacts.

Recommended flow:

```text
Provider chain
    -> normalize completed bars
    -> validate chronology/OHLC/count/freshness
    -> atomic data/<SYMBOL>.csv
    -> strategy calculations
    -> portfolio valuation
    -> enterprise KPI evidence
```

## Recommended provider policy

The Swing implementation uses this order:

```text
YFINANCE
-> STOOQ_READ_ONLY
-> ROBINHOOD_AGENT_READ_ONLY when an authenticated MCP runtime supplies the invoker
-> prior valid local CSV
```

Other plugins may select different providers, but must declare their deterministic order and preserve provider identity in evidence.

API-key providers such as Finnhub, Alpha Vantage, Twelve Data, Tiingo, or Polygon may be added behind the same interface. Credentials must come from protected server environment files and must never be committed.

## Stable daily CSV contract

```text
Date,Open,High,Low,Close,Adj Close,Volume
```

Rules:

- oldest to newest;
- unique dates;
- completed sessions only;
- finite positive OHLC prices;
- High >= Open/Close/Low;
- Low <= Open/Close/High;
- nonnegative integer volume;
- at least 51 completed bars;
- target at least 250 completed bars;
- `Adj Close` must disclose whether it is provider-adjusted or copied from Close.

## Required evidence fields

A plugin refresh report should include:

- generated_at;
- requested symbols;
- required and optional symbols;
- provider order;
- provider attempts per symbol;
- selected provider;
- fetch status;
- validation status;
- publication status;
- bar count;
- latest completed date;
- freshness status;
- adjusted_close_source;
- corporate_action_adjusted;
- warnings and errors;
- permanent safety flags.

## Required versus optional symbols

Required symbols should include benchmarks, open portfolio positions, and configured strategy symbols. Required failure blocks the strategy cycle only after every provider and prior valid local file are unusable.

Watchlist and candidate symbols may be optional. Their failure produces warnings without invalidating unrelated strategy evidence.

## Broker separation

A broker adapter and a market-data provider are separate responsibilities.

Broker responsibilities:

- orders and cancellations after live governance approval;
- fills;
- positions;
- balances;
- execution audit.

Market-data responsibilities:

- historical OHLCV;
- current quotes;
- corporate-action disclosure;
- technical-indicator inputs;
- data freshness.

Even when a strategy eventually uses Robinhood for live execution, historical analytics may continue to use independent validated providers. Broker quotes may be used as a read-only fallback or reconciliation source.

## AI CIO onboarding requirement

Each plugin registration should declare read-only paths for:

- market-data refresh status;
- provider health;
- strategy reports that depend on market data;
- enterprise KPI evidence.

The host AI CIO should display stale or blocked plugin status independently. One plugin's provider failure must not invalidate another plugin or the Dividend strategy.

## Migration checklist for existing plugins

1. Inventory every calculation that reads prices.
2. Identify static, manually copied, or stale files.
3. Add the provider interface and ordered chain.
4. Add completed-session filtering.
5. Add stable CSV normalization.
6. Add atomic writes and prior-file preservation.
7. Add required/optional symbol resolution.
8. Add freshness blocking before valuation.
9. Add provider identity to reports.
10. Run a controlled refresh and compare values against an independent source.
11. Schedule refresh before valuation, KPI publication, dashboard refresh, and email delivery.
12. Keep live trading disabled until separate execution governance is approved.

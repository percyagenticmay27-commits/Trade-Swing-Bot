# Enterprise Market Data Valuation Fallback Version 1.0

Authoritative implementation owner: Dividend AI CIO Enterprise Market Data Provider.

## Consumer rule for SWING-001

When a live quote is unavailable but Enterprise history is fresh, the provider may publish:

```text
source_type=HISTORICAL_CLOSE_FALLBACK
valuation_fallback=true
status=WARNING
```

The `price` is the latest validated historical `adjusted_close`, or `close` when adjusted close is unavailable. This is a provider-generated valuation value, not a real-time quote.

Swing may use it for current valuation, market value, unrealized P&L, executive summary, KPI evidence, and daily email while preserving the warning and source type.

Swing must still block when history is stale, unavailable, empty, malformed, or has no usable latest close. Swing must not relabel the fallback as intraday or real-time data.

No Swing strategy calculations, allocation rules, stale-history protection, or paper-only behavior change.

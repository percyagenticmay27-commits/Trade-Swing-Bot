# Enterprise Contracts

This directory contains documentation-only copies of shared Enterprise contracts consumed by the Swing Bot.

## Authoritative owner

The Dividend AI CIO repository is the source of truth for the Enterprise Market Data Provider:

```text
percyagenticmay27-commits/Trade-Dividend-Bot
```

Authoritative branch during Version 1.0 handoff:

```text
feature/enterprise-market-data-provider-v1
```

## Included documents

- `ENTERPRISE_MARKET_DATA_PROVIDER_V1.md`
- `SWING_PHASE_2_ENTERPRISE_MARKET_DATA_MIGRATION_GUIDE.md`

These files are copied into the Swing repository so Swing development can proceed without importing Dividend production code.

## Rules

- Documentation copies do not transfer ownership of provider selection, caching, freshness, normalization, health, or Robinhood/Codex integration to Swing.
- Swing must remain provider-neutral.
- Swing must not import Dividend production modules.
- Swing must preserve stale-data rejection.
- The existing `$4,500` `SWING-001` allocation must remain unchanged.
- When a shared contract changes, update the authoritative Dividend document first, then refresh this documentation copy.

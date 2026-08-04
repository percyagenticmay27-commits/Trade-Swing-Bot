# Twelve Data Provider Version 1 — Consumer Notice

The Dividend AI CIO now uses this production precedence for shared market data:

1. YFINANCE
2. TWELVE_DATA when configured
3. Fresh LOCAL_CACHE
4. ROBINHOOD_MCP through Codex
5. Historical-close valuation fallback or safe failure

Swing remains provider-neutral. It must consume only the normalized Enterprise status, quote, and history-export contracts. Swing must not read `TWELVE_DATA_API_KEY`, call Twelve Data directly, or change its calculations because of this provider addition.

The authoritative implementation and secret configuration remain in the Dividend AI CIO repository. Existing SWING-001 stale-data rejection, paper-only behavior, and the $4,500 allocation remain unchanged.

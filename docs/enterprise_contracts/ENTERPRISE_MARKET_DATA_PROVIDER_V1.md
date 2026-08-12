# Enterprise Market Data Provider Version 1.0

AI CIO-owned, strategy-neutral, read-only market-data service.

## Cost-aware provider precedence

Routine public market-data operations use:

1. yfinance
2. Stooq
3. prior valid normalized local cache
4. Robinhood MCP through root's authenticated `/usr/local/bin/codex exec` profile
5. safe failure

Robinhood is intentionally next to last because Codex usage is quota-controlled. The service does not invoke Codex when yfinance, Stooq, or a fresh cache can satisfy both quote and history requirements.

Freshness is mandatory. Stale cache or provider data is rejected. A required-symbol failure blocks only the requesting strategy; an optional-symbol failure is a warning.

## Contract

`get_quote`, `get_history`, `get_latest_close`, `get_previous_close`, `get_volume`, `get_split_history`, and `get_dividend_history`.

The provider owns selection, normalization, freshness, cache validation, health, and evidence. Strategy repositories do not know which upstream provider succeeded.

## Two-pass conditional Robinhood bridge

The server's Robinhood OAuth connection belongs to root's Codex profile. Authentication files are never copied to the repository or to the `tradebot` account.

The systemd service performs three sequential actions:

1. An unprivileged public/cache pass runs as `tradebot` with Robinhood disabled. It uses yfinance, Stooq, and fresh cache only.
2. A tightly scoped root command reads the first-pass evidence. It invokes Codex/Robinhood only for quote or history operations that remain unresolved.
3. A final unprivileged pass repeats the cost-aware provider chain and may consume the newly written Robinhood handoff only after the public providers and fresh cache remain unavailable.

The conditional root bridge:

- accepts only `get_quote` and `get_history`;
- invokes `/usr/local/bin/codex exec` with root's existing authenticated profile;
- rejects order, buy, sell, cancel, transfer, position, and execution operations;
- uses strict timeouts and fails closed for each Robinhood attempt;
- rejects OAuth, token, cookie, secret, authorization, and account-number fields;
- atomically writes mode `0640` normalized JSON into `/run/enterprise-market-data-handoff` only after a successful response;
- changes only the handoff file ownership to `tradebot:tradebot`;
- never exposes `/root/.codex` to the unprivileged runtime.

A Codex usage limit, MCP outage, authentication failure, timeout, malformed response, or missing handoff does not bypass freshness protection. If no fresh source succeeds, the affected strategy is blocked safely.

## Runtime and persistent cache ownership

Transient Robinhood handoff files are managed by systemd through:

```ini
RuntimeDirectory=enterprise-market-data-handoff
```

They live under `/run/enterprise-market-data-handoff` and are recreated for service execution.

The freshness-validated fallback cache is persistent and managed by systemd through:

```ini
StateDirectory=enterprise-market-data-cache
```

It lives under `/var/lib/enterprise-market-data-cache`. The service does not depend on a repository-local `runtime/` directory. No strategy allocation, portfolio state, OAuth material, or broker information is stored in the cache.

## Evidence

- `results/enterprise_market_data_status.json`
- `results/enterprise_market_data_provider_health.json`
- `results/enterprise_market_data_refresh.csv`
- `results/enterprise_market_data_contract.json`

The contract publishes policy `PUBLIC_FIRST_COST_AWARE_ROBINHOOD_FALLBACK` and precedence:

```text
YFINANCE -> STOOQ -> LOCAL_CACHE -> ROBINHOOD_MCP -> SAFE_FAILURE
```

## Deployment

Dividend AI CIO deployment root:

```text
/home/tradebot/Trade-Dividend-Bot
```

Install and run:

```bash
sudo cp deploy/systemd/enterprise-market-data-refresh.service \
  /etc/systemd/system/enterprise-market-data-refresh.service
sudo systemctl daemon-reload
sudo systemctl start enterprise-market-data-refresh.service
sudo systemctl status enterprise-market-data-refresh.service
```

Systemd-managed paths:

```text
/run/enterprise-market-data-handoff
/var/lib/enterprise-market-data-cache
```

Review logs:

```bash
sudo journalctl -u enterprise-market-data-refresh.service --no-pager -n 150
```

## Swing Phase 2 integration

1. Read `/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_contract.json` and treat Version 1.0 as the stable host contract.
2. Replace direct local-CSV primary reads with a Swing-owned read-only adapter consuming AI CIO-published normalized output.
3. Use normalized quote/history fields for portfolio valuation, indicators, performance, executive summary, KPI evidence, and email.
4. Preserve Swing stale-data rejection. Never silently fall back to stale Swing CSV files.
5. Required-symbol failures block only `SWING-001`; optional-symbol failures remain warnings.
6. Preserve the existing `$4,500` allocation and all Swing calculations.

## Source of truth

This is a documentation copy for the Swing repository. The authoritative document is maintained in:

```text
Trade-Dividend-Bot/docs/ENTERPRISE_MARKET_DATA_PROVIDER_V1.md
```

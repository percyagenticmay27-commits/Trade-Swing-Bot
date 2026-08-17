# Swing Bot to AI CIO Handoff Addendum — Enterprise Discovery Bucket

Last updated: 2026-08-17

## Product decision

The Enterprise AI CIO owns broad market discovery intelligence and may publish a weekly bucket of underlying stocks/sectors classified as HOT, RISING, EMERGING, COOLING, or DECLINING.

Swing remains the sole authority for Swing lifecycle state. AI CIO nomination never directly creates WATCHLIST, LOW, MEDIUM, HIGH, allocation, entry, exit, BUY, SELL, or paper-position state.

The intended authority chain is:

AI CIO discovery bucket -> Swing explicit leveraged mapping -> Swing DISCOVERY candidate -> existing Discovery Engine evidence/confluence lifecycle -> Opportunity Quality -> Entry Score -> paper lifecycle.

## Implemented Swing-side intake

New module:

- `main/src/swing_trade_bot/enterprise_discovery_bucket.py`

New mapping configuration:

- `main/configs/swing_discovery_leveraged_mapping.json`

New regression suite:

- `main/tests/test_enterprise_discovery_bucket.py`

Launcher integration:

- `main/run_swing_bot_cycle.py` now materializes Enterprise discovery runtime inputs before market-data refresh and the normal Swing cycle.

Daily-cycle input configuration:

- `results/discovery_candidates_runtime.csv`
- `results/discovery_mentions_runtime.csv`

The intake publishes diagnostic evidence to:

- `results/enterprise_discovery_intake_report.json`

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

Optional evidence may include:

- themes
- source-level evidence entries
- source
- mentioned_on
- earnings-growth relevance
- analyst-upgrade relevance

Only HOT, RISING, and EMERGING can create a new Swing candidate. New candidates require an explicit Swing-owned underlying-to-leveraged mapping and always enter at `DISCOVERY` with zero paper history.

COOLING and DECLINING do not create new candidates. Existing Swing candidates may consume bucket themes/evidence but retain their Swing-owned lifecycle/performance state.

If the AI CIO bucket does not yet exist, Swing safely materializes the existing local candidate and mention inputs unchanged using `SWING_LOCAL_FALLBACK`.

Malformed Enterprise evidence fails closed.

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
- no Opportunity Quality Version 1.2 changes

## Validation status

Repository changes are committed on `feature/swing-phase2-enterprise-market-data`.

Focused DigitalOcean validation is required before deployment acceptance:

```bash
cd /home/tradebot/Trade-Swing-Bot/main
source .venv/bin/activate

python -m py_compile \
  src/swing_trade_bot/enterprise_discovery_bucket.py \
  run_swing_bot_cycle.py

pytest \
  tests/test_enterprise_discovery_bucket.py \
  tests/test_run_swing_bot_cycle.py \
  -v
```

Then run the intake alone before the full cycle and inspect the diagnostic artifact:

```bash
python - <<'PY'
from swing_trade_bot.enterprise_discovery_bucket import refresh_enterprise_discovery_inputs
import json

print(json.dumps(refresh_enterprise_discovery_inputs(), indent=2))
PY
```

Until the Dividend-hosted AI CIO publishes `results/enterprise_swing_discovery_bucket.json`, expected source mode is `SWING_LOCAL_FALLBACK`. Once the producer exists, expected source mode is `AI_CIO_BUCKET_PLUS_SWING_LOCAL`.

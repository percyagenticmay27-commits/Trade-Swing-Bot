# Enterprise Market Data Historical Bar Export Version 1.0

The Dividend AI CIO now exports actual normalized historical bars for `SWING-001` instead of publishing history metadata only.

Authoritative DigitalOcean directory:

```text
/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_history
```

Required files:

```text
SOXL.history.json
SOXL.csv
TQQQ.history.json
TQQQ.csv
```

CSV schema:

```csv
date,open,high,low,close,adjusted_close,volume
```

JSON exports contain provider-neutral metadata plus the complete normalized `bars` array. Both JSON and CSV files are written atomically.

The corresponding symbol record in:

```text
/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_status.json
```

contains:

```text
bars_json_path
bars_csv_path
```

Swing Phase 2 may use the exported CSV files to create or refresh its local `data/SOXL.csv` and `data/TQQQ.csv` compatibility files. Swing must still:

- validate contract schema Version 1.0;
- require `SWING-001` status `READY` or an allowed `WARNING`;
- reject stale quote or history data;
- preserve its existing stale-data protection;
- never substitute entry price for missing current price;
- never silently use an older local CSV when the Enterprise export is missing or blocked;
- remain provider-neutral;
- preserve the existing `$4,500` allocation.

The Dividend AI CIO remains the authoritative owner of data acquisition, precedence, normalization, freshness, caching, health, and Robinhood/Codex fallback.

# Swing CIO Plugin Manifest

## Purpose

The Swing CIO Plugin Manifest registers Trade-Swing-Bot as a descriptive, paper-only strategy plugin for the Enterprise AI CIO platform.

The manifest allows the CIO to identify the plugin, understand its capabilities, locate its published reports, map reports to dashboard destinations, and enforce permanent safety boundaries.

The manifest does not run Swing engines, change calculations, transform existing reports, place orders, move capital, connect to a broker, or write directly to PostgreSQL.

## Files

- `configs/swing_cio_plugin_manifest.json`
- `src/swing_trade_bot/swing_cio_plugin_manifest.py`
- `tests/test_swing_cio_plugin_manifest.py`

## Plugin Identity

- Plugin ID: `SWING-001`
- Plugin name: `Trade-Swing-Bot`
- Plugin type: `STRATEGY_PLUGIN`
- Strategy class: `SWING_TRADING`
- Repository role: `INDEPENDENT_STRATEGY_INTELLIGENCE_PLUGIN`
- Registration status: `CIO_DISCOVERABLE`

The plugin ID and repository identity are stable registration values. A future version update may change `plugin_version`, but must not silently create a new plugin identity.

## Registration Lifecycle

The manifest is loaded by path and validated before the CIO treats the plugin as discoverable.

A valid manifest must contain:

- identity metadata
- version metadata
- lifecycle and runtime status
- a non-empty capability catalog
- a non-empty published report catalog
- immutable safety declarations
- compatibility and ownership declarations

Manifest validation is metadata-only. Validation does not start or schedule any Swing engine.

## Capability Catalog

Each capability includes:

- stable capability ID
- display name
- availability status
- advisory-only declaration

Duplicate capability IDs are invalid.

The current catalog covers discovery, watchlist intelligence, theme momentum, source confluence, market intelligence, market regime, momentum scoring, opportunity quality, allocation recommendations, strategy assignment, position intelligence, thesis monitoring, historical archives, and executive reporting.

## Published Report Catalog

Each report declaration includes:

- report ID
- report name
- owning module
- required or optional classification
- artifact paths
- CIO dashboard destination

Duplicate report IDs are invalid.

Milestone 1 treats currently declared reports as optional runtime artifacts. Their absence creates warnings rather than invalidating plugin identity. A future deployment profile may mark selected operational reports as required after scheduling and runtime ownership are formally established.

## Artifact Formats

Current descriptive registrations may reference:

- JSON
- CSV
- Markdown
- HTML archive summaries
- ZIP historical archives

The manifest does not alter any artifact contents or schemas.

## Safety Guarantees

The following values are immutable for this milestone:

```text
paper_trade_mode: true
advisory_only: true
reporting_only: true
live_trading_enabled: false
broker_execution_enabled: false
order_placement_enabled: false
capital_movement_enabled: false
broker_connection_enabled: false
robinhood_execution_enabled: false
investor_controls_live_mode: true
postgres_required: false
```

Changing any of these values causes validation failure.

Plugin discovery is not strategy activation. A visible dashboard entry does not authorize live trading, brokerage access, capital movement, or order placement.

## Dashboard Compatibility

The manifest maps existing Swing reports to CIO presentation destinations such as:

- Swing Strategy Overview
- Strategy Assignment
- Thesis Monitor
- Performance and Weekly Review
- Historical Evidence and Archive Health

These destinations are presentation metadata only. The CIO must read the existing report artifacts and must not independently reproduce Swing calculations.

## PostgreSQL Boundary

PostgreSQL is future AI CIO platform work.

Current flow:

```text
Swing engines
    -> existing JSON / CSV / Markdown outputs
    -> Swing plugin manifest
    -> CIO discovery and presentation
```

Future flow:

```text
Swing outputs
    -> AI CIO import service
    -> validation and transformation
    -> PostgreSQL
    -> enterprise dashboards and historical queries
```

The Swing plugin declares:

```text
database_owner: AI_CIO_PLATFORM
direct_database_writes: false
postgres_required: false
```

The Swing repository must not receive PostgreSQL credentials or direct database-write responsibilities during Milestone 1.

## Public Functions

### `load_plugin_manifest(path)`

Loads a UTF-8 JSON object and produces clear errors for missing files, malformed JSON, or a non-object root.

### `validate_plugin_manifest(manifest, repository_root=None)`

Validates identity, capabilities, reports, artifact formats, safety declarations, and compatibility boundaries.

When `repository_root` is provided:

- a missing optional artifact produces a warning
- a missing required artifact produces an error

### `build_manifest_summary(manifest)`

Builds a compact CIO-facing summary containing registration, capability counts, report counts, and key safety values.

It does not calculate investment or portfolio metrics.

## Validation Commands

Run from the repository root:

```bash
python -m py_compile main/src/swing_trade_bot/swing_cio_plugin_manifest.py
python -m unittest main/tests/test_swing_cio_plugin_manifest.py -v
```

Or use the repository's full test command:

```bash
python -m pip install -e ./main
python -m unittest discover -s main/tests -v
```

## Next Milestone

After this manifest passes QA, the next development component is the formal Swing CIO Output Contract.

The output contract will define field-level and column-level schemas for CIO-consumable artifacts while preserving every existing report format and calculation owner.

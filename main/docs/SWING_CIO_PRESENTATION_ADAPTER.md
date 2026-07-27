# Swing CIO Presentation Adapter

## Purpose

The Swing CIO Presentation Adapter converts existing paper-only Swing Bot report artifacts into normalized display models for the future AI CIO platform.

It is a presentation layer only. It does not modify source reports, recalculate trading intelligence, place orders, connect to a broker, move capital, or write directly to a database.

## Files

- `configs/swing_cio_presentation_adapter.json`
- `src/swing_trade_bot/swing_cio_presentation_adapter.py`
- `tests/test_swing_cio_presentation_adapter.py`

## Inputs

The adapter may read registered JSON artifacts including:

- Strategy Assignment Version 1.3
- Thesis Monitor Version 1.4
- Executive Dashboard Version 1.0.1
- Monthly Command Center Version 1.0
- Historical Archive Version 1.0.0

Each source is selected by its independent `artifact_id` and `artifact_version`.

## Outputs

- `results/swing_cio_presentation.json`
- `results/swing_cio_presentation.md`

These outputs are derived display artifacts. Original report files remain unchanged.

## Status Rules

- `READY`: all configured sources were available and readable.
- `READY_WITH_WARNINGS`: one or more optional sources were missing, unreadable, or unavailable.
- `ERROR`: a required source could not be presented.

Each section reports one of:

- `AVAILABLE`
- `UNAVAILABLE`
- `ERROR`

## Missing Inputs

Optional source files produce warnings and an unavailable section. They do not prevent other sections from being produced.

Required source files produce an error status.

## Registry Validation

When a Schema Registry is supplied, the adapter confirms the exact artifact ID and independent artifact version before reading the source.

Unknown or unregistered versions are not silently accepted.

## Normalization

Record-oriented reports can define:

- a `record_path`
- presentation `key_fields`
- a title
- a dashboard destination

Only declared key fields are copied into normalized records. Extra source fields remain in the original artifact and are not modified.

Summary-style reports are represented using top-level scalar metadata and section availability.

## Safety Guarantees

The following settings are mandatory:

- `paper_trade_mode=true`
- `advisory_only=true`
- `read_only_sources=true`
- `direct_database_writes=false`

The adapter cannot enable live trading or broker execution.

## Validation Commands

Run from the local `main` directory in Git CMD:

```cmd
python -m pip install -e .
python -m py_compile src\swing_trade_bot\swing_cio_presentation_adapter.py
python -m unittest tests\test_swing_cio_presentation_adapter.py -v
```

## Architecture Boundary

The Swing Bot owns source intelligence and its report artifacts.

The adapter owns normalization into presentation-ready models.

The future AI CIO platform owns UI rendering, persistence, cross-plugin aggregation, and any future PostgreSQL import process.

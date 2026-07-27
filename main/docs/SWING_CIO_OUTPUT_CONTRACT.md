# Swing CIO Output Contract

## Purpose

The Swing CIO Output Contract is the formal interface between the paper-only Trade-Swing-Bot repository and the future AI CIO Platform.

It describes existing output artifacts. It does not change engine calculations, rewrite report schemas, place orders, connect to a broker, or write directly to PostgreSQL.

## Strict Artifact Versioning

The repository uses `STRICT_ARTIFACT_VERSIONING`.

Each artifact keeps its own independent version. A repository release does not automatically change every report version.

Examples:

- Strategy Assignment JSON: Version 1.3
- Thesis Monitor JSON: Version 1.4
- Executive Dashboard JSON: Version 1.0.1
- Monthly Command Center JSON: Version 1.0
- Historical Archive Manager JSON: Version 1.0.0

This allows the CIO Platform to support older stable report contracts while newer modules evolve independently.

## Permanent Compatibility Rules

The following changes are backward compatible:

- Adding optional fields
- Adding optional artifacts
- Adding new enum values only when the consumer is explicitly designed to tolerate unknown values
- Adding new dashboard presentation metadata

The following changes require a major artifact version increase:

- Removing a field
- Renaming a field
- Changing a field type
- Changing root JSON structure
- Reordering or removing required CSV columns
- Adding a new required field
- Changing the meaning of an existing field

## Contract Files

```text
configs/swing_cio_output_contract.json
src/swing_trade_bot/swing_output_contract.py
tests/test_swing_output_contract.py
docs/SWING_CIO_OUTPUT_CONTRACT.md
```

## Contract Metadata

The contract includes:

- Contract ID
- Plugin ID
- Contract schema version
- Versioning policy
- Supported formats
- Timestamp policy
- Compatibility policy
- Artifact registry
- Owner modules
- Dashboard destinations
- Missing-artifact behavior

## Artifact Rules

Every artifact must define:

- Unique artifact ID
- Unique repository-relative path
- Format
- Owner module
- Independent artifact version
- Schema version
- Required or optional status
- Dashboard destination
- Missing-artifact behavior

JSON artifacts also define their root type and required fields.

CSV artifacts define their columns in canonical order.

Markdown artifacts define required report sections.

## Missing Artifact Behavior

Optional artifacts use `WARN` and do not disable the plugin.

Required artifacts use `ERROR` and cause inventory validation to fail.

The current CIO compatibility artifacts are optional because many reports are generated only when their source pipeline runs.

## Timestamp Policy

The preferred timestamp field is:

```text
generated_at_utc
```

The preferred format is ISO-8601 UTC ending in `Z`.

Existing artifacts without a timestamp generate a warning rather than being rejected. Timestamp standardization belongs to a future intentional schema upgrade and must not be silently added to frozen report formats.

## Safety Guarantees

The output contract permanently requires:

```text
paper_trade_mode=True
advisory_only=True
direct_database_writes=False
```

The contract cannot enable:

- Live trading
- Broker execution
- Robinhood execution
- Order placement
- Capital movement
- Direct database ownership by the Swing Bot

The future AI CIO Platform owns any database import or persistence layer.

## Validation

The validator checks:

- Required contract metadata
- Strict versioning policy
- Independent compatibility policy
- Unique artifact IDs
- Unique artifact paths
- Supported formats
- Matching file extensions
- Valid artifact and schema versions
- Required owner modules
- Dashboard destinations
- Duplicate fields or columns
- JSON root declarations
- CSV column declarations
- Missing required and optional artifacts
- Paper-only and advisory-only boundaries

## Validation Commands for Git CMD

Run from the local `main` directory:

```cmd
python -m pip install -e .
python -m py_compile src\swing_trade_bot\swing_output_contract.py
python -m unittest tests\test_swing_output_contract.py -v
```

## Current Scope

Phase 9C documents verified high-value CIO artifacts first. Additional existing report families can be added after their exact schemas are verified from production modules.

The contract must never guess fields or silently normalize an existing frozen output.

## Next Phase

Phase 9D will create the Swing CIO Schema Registry. It will organize artifact schemas by artifact ID and version so the presentation adapter can select the correct parser without altering source reports.

# Swing CIO Schema Registry

## Purpose

The Swing CIO Schema Registry is the authoritative lookup layer for CIO-consumable Swing Bot artifacts. It selects schemas by the pair:

- `artifact_id`
- `artifact_version`

Repository releases do not override artifact versions.

## Safety Boundary

The registry is descriptive and validation-only.

- `paper_trade_mode=true`
- `advisory_only=true`
- `direct_database_writes=false`
- no brokerage connection
- no order placement
- no capital movement

## Files

- `configs/swing_cio_schema_registry.json`
- `src/swing_trade_bot/swing_schema_registry.py`
- `tests/test_swing_schema_registry.py`

## Strict Versioning

Each artifact evolves independently. For example:

- Strategy Assignment remains artifact version `1.3`
- Thesis Monitor remains artifact version `1.4`
- Executive Dashboard remains artifact version `1.0.1`
- Historical Archive remains artifact version `1.0.0`

A future repository release does not change those values unless the artifact itself changes.

## Registration Key

The unique registration key is:

```text
(artifact_id, artifact_version)
```

Duplicate keys are invalid.

## Supported Statuses

- `ACTIVE` — available for current CIO consumption
- `DEPRECATED` — readable for backward compatibility but no longer preferred

Deprecated registrations should declare a replacement.

## Public Functions

### `load_schema_registry(path)`

Loads the JSON registry and requires an object at the root.

### `validate_schema_registry(registry)`

Validates identity, safety locks, version syntax, unique registration keys, formats, owner modules, dashboard destinations, statuses, and JSON root declarations.

### `get_schema_registration(registry, artifact_id, artifact_version)`

Returns the exact registered schema metadata. Unknown artifact/version pairs raise `KeyError`.

### `list_artifact_versions(registry, artifact_id)`

Returns all registered versions in numeric version order.

### `get_latest_active_registration(registry, artifact_id)`

Returns the highest active artifact version. It does not use the repository version.

### `is_schema_compatible(...)`

Returns whether the requested artifact version and schema version are registered together.

### `build_registry_summary(registry)`

Returns CIO-safe registry summary metadata.

## Compatibility Rules

- Historical versions may remain registered.
- New versions are added; old registrations are not silently rewritten.
- Unknown versions fail closed.
- Multiple active versions are allowed but generate a warning.
- Removing, renaming, or changing required fields belongs in a new major artifact version.

## Validation

Run from the `main` directory in Git CMD:

```cmd
python -m pip install -e .
python -m py_compile src\swing_trade_bot\swing_schema_registry.py
python -m unittest tests\test_swing_schema_registry.py -v
```

## Next Phase

The Schema Registry feeds Phase 9E, the CIO Presentation Adapter. The adapter will consume registered artifacts and transform them into normalized CIO view models without changing source reports.

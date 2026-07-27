# Swing Strategy Service Registration

## Purpose

This module exports the Trade Swing Bot as a strategy service record compatible with the AI CIO Enterprise Service Registry and the governed paper-capital allocation workflow already used by the Dividend platform.

The registration is descriptive only. It does not place orders, contact a broker, move capital, activate a strategy, or write directly to the CIO database.

## Source of Truth

The registration is built from:

```text
configs/swing_cio_plugin_manifest.json
```

The manifest remains the source of truth for plugin identity, version, runtime status, strategy class, and permanent safety boundaries.

## Output

```text
results/swing_strategy_service_registration.json
```

## CIO Discovery Fields

The output exposes the flexible fields consumed by the Dividend platform strategy discovery process:

```text
strategy_id
plugin_id
service_id
name
display_name
service_type
plugin_type
strategy_class
status
runtime_status
health
health_status
enabled
strategy_plugin
paper_trade_mode
paper_compatible
version
module_version
```

## Eligibility Rules

A Swing strategy registration is discoverable only when:

- `enabled=True`
- `strategy_plugin=True`
- `paper_trade_mode=True`
- `paper_compatible=True`
- status is one of `ONLINE`, `ENABLED`, `AVAILABLE`, `HEALTHY`, or `READY`
- `advisory_only=True`
- `reporting_only=True`

## Permanent Safety Boundaries

The validator requires:

```text
live_trading_enabled=False
broker_execution_enabled=False
capital_movement_enabled=False
automatic_activation_allowed=False
direct_database_writes=False
governance_review_required=True
database_owner=AI_CIO_PLATFORM
```

## Integration Flow

```text
Swing CIO Plugin Manifest
        ↓
Swing Strategy Service Registration
        ↓
AI CIO Enterprise Service Registry
        ↓
Dynamic Strategy Discovery
        ↓
Investor Paper-Capital Allocation
        ↓
PENDING_GOVERNANCE_REVIEW
```

## Public Functions

```python
load_plugin_manifest(...)
build_strategy_service_registration(...)
validate_strategy_service_registration(...)
is_discoverable_by_cio(...)
write_strategy_service_registration(...)
build_and_write_strategy_service_registration(...)
```

## Local Validation

From the repository `main` folder in Git CMD:

```cmd
python -m pip install -e .
python -m py_compile src\swing_trade_bot\swing_strategy_service_registration.py
python -m pytest tests\test_swing_strategy_service_registration.py -v
```

## Future CIO Boundary

The Swing repository owns strategy intelligence and its exported registration file. The AI CIO platform owns registry ingestion, database persistence, investor allocation requests, governance approval, and any future strategy activation workflow.

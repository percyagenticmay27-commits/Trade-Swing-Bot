# Swing CIO Integration Roadmap

## Purpose

Define the controlled path for integrating the paper-only Trade Swing Bot with the AI CIO platform while preserving independent repository ownership, strict artifact versioning, advisory-only behavior, and investor governance.

## Completed Foundation

- Version 1.0 Reporting Layer
- Version 1.1 Intelligence Layer
- Version 1.2 Opportunity Quality Engine
- Version 1.3 Position Intelligence
- Version 1.4 Thesis Monitor
- Historical Archive Manager

## CIO Compatibility Milestone 1

### Phase 9A — Artifact Inventory
Status: Complete

### Phase 9B — Plugin Manifest
Status: Complete and locally validated

### Phase 9C — Output Contract
Status: Complete and locally validated

### Phase 9D — Schema Registry
Status: Complete and locally validated

### Phase 9E — CIO Presentation Adapter
Status: Complete and locally validated

### Phase 9E.1 — Enterprise Strategy Registry Export
Status: Complete and locally validated

### Phase 9E.2 — Strategy Capability Profiles
Status: Complete and locally validated through Version 1.4 policy

### Phase 9E.3 — Independent Committee Governance
Status: Complete and locally validated — 28 governance tests and 39 capability-profile tests passed

Frozen committee order:

```text
Discovery Committee
        ↓
Opportunity Committee
        ↓
Entry Committee
        ↓
Portfolio Committee
        ↓
Exit Committee
```

Permanent rules include independent Entry veto authority, no sector/theme/history/concentration bias, no fixed position count, and SGOV for unallocated paper capital.

### Phase 9E.4 — Committee Decision Traceability
Status: Complete and locally validated — 40 traceability tests passed; combined committee suite 107 passed

Deterministic append-only traces preserve evidence snapshots, reason codes, source lineage, committee order, bias audits, and later outcome attachments without hindsight rewriting.

### Phase 9E.5 — Governed Committee Learning Foundation
Status: Complete and locally validated — 39 focused learning tests passed; combined committee suite 146 passed

Learning remains observation-only until 30 completed traces, 6 months, and 10 observations per committee. Decision quality and outcome quality remain separate. All proposals require human approval and cannot change policy automatically.

### Phase 9F — Full CIO Validation Suite
Status: Complete and locally validated — 40 focused validation tests passed; combined CIO committee-validation suite 186 passed

The suite validates the manifest, output contract, schema registry, presentation adapter, strategy registration, capability profiles, governance, traceability, learning, strict versions, identity consistency, discovery compatibility, and all safety locks.

### Phase 9F.1 — CIO Acceptance Test
Status: Complete and locally validated — 28 focused acceptance tests passed; complete pre-freeze suite 214 passed

Acceptance verifies enterprise discovery, plugin registration, Phase 9F readiness, committee governance, deterministic decision replay, governed learning, and the paper-only safety boundary. Final result must be `READY_FOR_CIO`.

### Phase 9G — Milestone 1 Freeze
Status: Complete and locally validated

Freeze requires Phase 9F `READY`, governance health 100, and Phase 9F.1 `READY_FOR_CIO`.

## Phase 10 — AI CIO Platform Integration

### Phase 10A — Same-Server Local Filesystem Registration
Status: Complete and locally validated — 29 focused integration tests passed; combined freeze/integration suite 53 passed

The Swing Bot and AI CIO will run on the same DigitalOcean server:

```text
/home/tradebot/
├── Trade-Dividend-Bot/
├── Trade-Swing-Bot/
└── AI-CIO/
```

Generated registration:

```text
results/swing_local_filesystem_registration.json
```

Required architecture:

- `transport=LOCAL_FILESYSTEM`
- AI CIO reads Swing artifacts locally and does not import Swing Python modules
- plugin root `/home/tradebot/Trade-Swing-Bot/main`
- artifact root `/home/tradebot/Trade-Swing-Bot/main/results`
- AI CIO validates `plugin_id=SWING-001`
- AI CIO requires acceptance status `READY_FOR_CIO`
- AI CIO reads only contracted final JSON artifacts
- file modification times determine freshness
- `.tmp` files are ignored
- Swing artifacts are written and validated before atomic `os.replace`
- both applications run as non-root user `tradebot`
- no API, network service, database connection, or Agentic transport is required for Milestone 1

### Phase 10A.1 — Unified Daily Cycle Launcher
Status: Implemented; local validation pending

Files:

```text
configs/swing_daily_cycle.json
src/swing_trade_bot/swing_daily_cycle.py
run_swing_bot_cycle.py
tests/test_swing_daily_cycle.py
docs/SWING_DAILY_CYCLE.md
```

The launcher provides one authoritative command for server execution:

```text
python run_swing_bot_cycle.py
```

It atomically publishes CIO contracts, checks strategy-owned reports, runs validation and acceptance, preserves the Milestone 1 freeze, and publishes the local registration last only after every readiness gate passes. A blocked cycle returns process exit status 1 and never publishes a misleading discovery registration.

### Phase 10B — AI CIO Registry Consumer
Status: Planned after Swing deployment-readiness blockers are resolved

Implement the matching read-only registry entry and local artifact reader in the independent AI-CIO repository. The CIO will display Swing status, freshness, governance health, and contracted recommendations without executing Swing code.

## Remaining Swing Deployment Readiness

```text
✓ 1. Unified daily cycle launcher — implemented; local validation pending
⬜ 2. Persistent paper portfolio state
⬜ 3. Market-data refresh and input contract
⬜ 4. Generate all runtime strategy reports through the unified cycle
⬜ 5. Server-readiness validator
⬜ 6. systemd service and timer package
⬜ 7. Production-code audit for superseded strategy rules
```

## Future Phases

### Phase 11 — Operational Automation
Schedule report generation, health checks, registry refresh, validation, trace generation, outcome attachment, atomic publication, and governed notifications.

### Phase 12 — CIO Paper-Production Acceptance
Reserved for later acceptance after the AI-CIO repository consumes the local Swing registration.

### Phase 13 — PostgreSQL Import
Future CIO-owned persistence only. The Swing repository will not write directly to PostgreSQL.

### Phase 14 — Historical Learning
Expand governed historical learning after the Milestone 1 committee-learning foundation is frozen and validated.

### Phase 15 — Future Live Readiness
Separate future milestone requiring explicit investor authorization. No live trading, broker execution, or capital movement is included in the current roadmap.

## Current Development Sequence

```text
Phase 10A.1 unified-cycle local validation
        ↓
Persistent paper portfolio state
        ↓
Market-data input contract
        ↓
Server-readiness and systemd deployment package
        ↓
Deploy Swing Bot beside Dividend Bot and AI CIO
        ↓
Phase 10B AI-CIO registry consumer
```

## Permanent Rules

- `paper_trade_mode=True`
- no Robinhood execution
- no brokerage communication
- no real order placement
- no real capital movement
- no automatic strategy activation
- no automatic policy, threshold, or weight changes
- investor governance remains required
- Swing and Dividend remain independent repositories
- strict artifact versioning remains mandatory
- original decision traces are immutable
- later outcomes and learning records are append-only
- decision quality remains separate from outcome quality
- AI CIO owns registry ingestion and future database persistence
- Entry Score remains independent from Opportunity Quality
- no sector, theme, concentration, stock-history, reputation, or market-regime hard bias
- Milestone 1 integration transport is local filesystem only
- AI CIO is a read-only artifact consumer and must not import Swing runtime modules

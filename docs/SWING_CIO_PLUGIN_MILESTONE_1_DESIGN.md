# Swing CIO Plugin Milestone 1 Design

## 1. Purpose

Define the first compatibility milestone that registers Trade-Swing-Bot as a governed strategy plugin for the Enterprise AI CIO platform while preserving the existing Swing Bot architecture, calculations, reports, repositories, and paper-only safety boundaries.

This milestone is descriptive and compatibility-focused. It does not transform Swing analytics, replace existing report formats, introduce PostgreSQL, or move CIO decision-making into the Swing Bot.

## 2. Architectural Position

The Trade-Dividend-Bot repository is the Enterprise AI CIO host platform.

The Trade-Swing-Bot repository remains an independent strategy-intelligence repository and becomes a discoverable CIO strategy plugin.

The repositories remain separate:

```text
Trade-Dividend-Bot
    Enterprise AI CIO host platform
    Service registry
    Plugin discovery
    Shared UI templates and navigation
    Investor and executive dashboards
    Cash and allocation workflows
    Future PostgreSQL ownership

Trade-Swing-Bot
    Swing strategy plugin
    Swing discovery and analysis
    Opportunity quality and entry timing
    Portfolio risk and position lifecycle
    Strategy assignment and thesis monitoring
    Historical evidence and reports
    Existing JSON, CSV, and Markdown artifacts
```

## 3. Milestone Scope

Milestone 1 will:

1. Register the Swing Bot as a CIO strategy plugin.
2. Preserve the existing Swing architecture unchanged.
3. Preserve existing JSON, CSV, and Markdown artifacts unchanged.
4. Define a formal descriptive plugin manifest.
5. Define a formal descriptive output contract.
6. Declare schema versions for CIO-consumable outputs.
7. Declare permanent paper-only and advisory-only safety flags.
8. Define compatibility with the existing CIO dashboard templates, navigation, cards, tables, warnings, report links, accessibility conventions, and plugin-health presentation.
9. Keep all Swing-specific analytics and business logic inside the Swing repository.
10. Keep AI CIO platform operations, allocation authority, future persistence, and future PostgreSQL import ownership outside the Swing engines.

## 4. Explicit Non-Goals

Milestone 1 will not:

- rewrite any Swing engine
- change Swing scoring or ranking logic
- change public dataclasses or public function names
- change current JSON schemas
- change current CSV columns
- change current Markdown report layouts
- remove or replace existing reports
- add PostgreSQL
- add database drivers, migrations, models, or direct database writes
- introduce CIO investment decisions into Swing calculations
- activate strategies automatically
- allocate or move capital
- connect to Robinhood or any brokerage
- place real or paper broker orders
- merge Trade-Swing-Bot and Trade-Dividend-Bot
- modify Dividend Bot production code
- create competing dashboard calculations

## 5. Governing Architecture Rules

### 5.1 Single Source of Truth

Each existing Swing engine remains the single source of truth for the calculation it owns.

The plugin manifest, output contract, CIO adapters, and CIO-compatible UI metadata may describe, validate, route, summarize, or display existing outputs. They must not reimplement Swing calculations.

### 5.2 Descriptive Manifest Rule

The Swing plugin manifest describes the plugin as it exists.

It must not:

- transform report payloads
- rename existing fields
- calculate new investment scores
- reinterpret advisory results as execution instructions
- modify files produced by existing engines

### 5.3 Output Preservation Rule

Existing JSON, CSV, and Markdown outputs remain valid and continue to be written by their owning modules.

Any CIO-facing metadata must reference those artifacts without changing them.

### 5.4 Repository Boundary

Trade-Swing-Bot owns Swing strategy intelligence and its published artifacts.

Trade-Dividend-Bot owns the Enterprise AI CIO host platform, service registry, shared UI framework, investor workflows, future database import services, and future PostgreSQL integration.

### 5.5 Future Persistence Boundary

During Milestone 1, CIO integration is file-contract based:

```text
Swing engines
    -> existing JSON / CSV / Markdown
    -> Swing plugin manifest
    -> Swing output contract
    -> CIO plugin discovery and compatible presentation
```

Future PostgreSQL flow, outside this milestone:

```text
Swing JSON / CSV artifacts
    -> future AI CIO import service
    -> PostgreSQL tables
    -> CIO dashboards and historical queries
```

Swing engines must not be changed to write directly to PostgreSQL.

## 6. Plugin Identity Design

The formal manifest will include at minimum:

- `plugin_id`
- `plugin_name`
- `display_name`
- `plugin_type`
- `strategy_class`
- `plugin_version`
- `manifest_schema_version`
- `repository_name`
- `repository_role`
- `lifecycle_status`
- `runtime_status`
- `registration_status`
- `generated_by`
- `generated_at`

Recommended identity values:

```text
plugin_id: SWING-001
plugin_name: Trade-Swing-Bot
plugin_type: STRATEGY_PLUGIN
strategy_class: SWING_TRADING
repository_role: INDEPENDENT_STRATEGY_INTELLIGENCE_PLUGIN
registration_status: CIO_DISCOVERABLE
```

Final version and lifecycle values must be read from the current Swing repository rather than invented by the manifest generator.

## 7. Capability Design

The manifest will describe supported capabilities without changing their implementations.

Expected capability groups include:

### Opportunity Discovery

- discovery candidate analysis
- source confluence
- theme momentum
- watchlist intelligence

### Opportunity Evaluation

- opportunity quality
- momentum scoring
- conviction scoring
- market intelligence
- market regime support
- technical analysis inputs
- fundamental analysis inputs

### Entry and Position Management

- entry timing
- portfolio risk evaluation
- portfolio allocation recommendations
- position lifecycle analysis
- thesis monitoring
- strategy assignment

### Reporting and Learning

- stock performance reports
- weekly stock reports
- executive summaries
- strategy comparisons
- historical archive management
- historical evidence retrieval
- CIO-consumable advisory reports

Every capability entry should identify:

- capability ID
- display name
- owning module
- status
- advisory-only classification
- published outputs
- required and optional source artifacts

## 8. Input Contract Design

The manifest will distinguish:

### Required Inputs

Inputs without which a specific Swing module cannot produce a valid report.

### Optional Inputs

Inputs whose absence creates warnings, zero evidence, neutral handling, or reduced presentation according to the existing owning module's rules.

### Context Inputs

Existing outputs used for summaries, cross-module context, dashboard awareness, or advisory presentation.

Each input declaration will include:

- input ID
- artifact name
- expected path
- format
- schema version when known
- required or optional status
- consuming module
- missing-data behavior
- source owner

The contract must document existing missing-data behavior and must not replace it with a new global rule.

## 9. Published Report Catalog Design

The output contract will catalog every report the Swing Bot publishes and every artifact the CIO may consume.

Each report entry will include:

- report ID
- report name
- producer module
- report purpose
- update cadence when defined
- required source inputs
- optional source inputs
- artifact variants
- schema version
- CIO presentation destination
- ownership boundary
- safety classification

Each artifact variant will include:

- artifact ID
- relative path
- format: JSON, CSV, or Markdown
- media type
- schema version
- required fields or columns
- optional fields or columns
- record identifier fields
- timestamp fields
- enumerated status fields when applicable
- missing-data behavior
- human-readable or machine-readable classification
- CIO consumption purpose
- current-state or historical classification

## 10. Output Schema Versioning

Milestone 1 adds descriptive schema version declarations without changing existing payloads.

Rules:

1. Every CIO-consumable JSON and CSV artifact receives a declared schema version in the output contract.
2. Existing report content is not rewritten merely to embed a schema version.
3. If an existing payload already contains a version field, the contract references it.
4. If an existing payload lacks a version field, the contract maintains an external version declaration.
5. Markdown artifacts may use a report-layout version in the contract.
6. A schema version change is required only when a future change breaks field, type, enum, or column compatibility.
7. Additive metadata may use a minor version increase when it remains backward-compatible.

Recommended external version notation:

```text
<artifact-family>.v<major>.<minor>
```

Example:

```text
opportunity-quality.v1.2
strategy-assignment.v1.0
historical-archive.v1.0
```

Actual versions must be derived from current module constants, freeze documents, report metadata, or repository release documentation.

## 11. Safety Manifest Design

The plugin manifest must publish explicit immutable safety declarations:

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
```

Additional rules:

- Manifest registration cannot weaken these flags.
- Scheduled jobs cannot override these flags.
- UI actions cannot override these flags.
- CIO discovery cannot be interpreted as strategy activation.
- Allocation eligibility metadata cannot place orders or move capital.
- Any future live-mode design requires a separate governed milestone and explicit investor authorization.

## 12. CIO Service Registry Compatibility

The Swing plugin registration metadata should be compatible with the AI CIO Enterprise Service Registry and expose:

- plugin identity
- plugin version
- lifecycle and runtime status
- health status
- capability summary
- dashboard link metadata
- report index link metadata
- artifact availability summary
- warnings and validation errors
- safety status
- repository ownership

Registration remains metadata-only.

It must not:

- start Swing engines automatically unless an existing governed scheduler already owns that action
- activate investment strategies
- assign capital
- approve recommendations
- transform Swing advisory outputs into execution requests

## 13. CIO UI and Report Compatibility

Milestone 1 will define Swing-side compatibility with the UI conventions already used by the AI CIO platform.

### 13.1 Shared Presentation Standards

Swing presentation metadata should support:

- consistent platform navigation
- strategy-plugin identity header
- status and health badges
- summary cards
- metric cards
- warning and error banners
- risk flags
- review-required indicators
- data tables
- report links
- artifact download links
- empty-state messaging
- generated-at timestamps
- responsive layout
- accessible labels and table headings

### 13.2 Page Ownership

The AI CIO Portal owns platform navigation and plugin discovery.

The Swing plugin owns Swing-specific presentation metadata and report content.

Proposed Swing CIO presentation destinations:

- Swing Strategy Overview
- Opportunity Quality
- Watchlist and Discovery
- Entry Timing
- Portfolio Risk and Allocation Recommendations
- Position Lifecycle
- Strategy Assignment
- Thesis Monitor
- Performance and Weekly Review
- Historical Evidence and Archive Health

These are presentation destinations, not new calculation engines.

### 13.3 No Competing Calculations

CIO-compatible pages must read existing Swing artifacts.

They must not independently calculate:

- opportunity quality
- entry scores
- allocation recommendations
- risk scores
- lifecycle states
- strategy assignment decisions
- thesis health
- performance metrics

## 14. Proposed Milestone Files

After design approval, implementation should be limited to new compatibility files such as:

```text
configs/swing_cio_plugin_manifest.json
configs/swing_cio_output_contract.json
src/swing_trade_bot/swing_cio_plugin_manifest.py
src/swing_trade_bot/swing_cio_output_contract.py
src/swing_trade_bot/swing_cio_presentation_adapter.py
tests/test_swing_cio_plugin_manifest.py
tests/test_swing_cio_output_contract.py
tests/test_swing_cio_presentation_adapter.py
docs/SWING_CIO_PLUGIN_MILESTONE_1_FREEZE.md
```

Exact filenames should be confirmed against existing repository naming conventions before implementation.

No existing production engine should be modified unless a later review identifies a strictly necessary, non-transformative compatibility bug and the investor explicitly approves that separate change.

## 15. Validation Plan

Milestone validation should prove:

### Manifest Validation

- manifest is valid JSON
- required identity fields exist
- plugin ID is stable
- capabilities reference existing modules or reports
- input declarations are complete
- published reports reference existing artifacts or explicitly documented optional artifacts
- schema versions are present
- safety flags are exact and immutable

### Output Contract Validation

- every current CIO-consumable JSON artifact is cataloged
- every current CIO-consumable CSV artifact is cataloged
- every current CIO-consumable Markdown artifact is cataloged
- producer ownership is documented
- paths are repository-relative
- required and optional fields are documented
- missing-data behavior matches current module behavior
- no report file is modified during contract generation

### Presentation Compatibility Validation

- adapter reads existing outputs only
- adapter does not duplicate calculations
- adapter produces CIO-compatible presentation metadata
- missing optional artifacts produce warnings rather than unsafe actions
- no allocation, execution, or capital movement actions exist

### Regression Validation

- existing Swing tests continue to pass
- existing JSON outputs remain byte-compatible unless generated timestamps naturally differ
- existing CSV headers remain unchanged
- existing Markdown layouts remain unchanged
- no Dividend Bot file is changed
- no PostgreSQL dependency is introduced

## 16. Implementation Sequence

### Phase 1A — Inventory

1. Read current Swing architecture, governance, freeze, workflow, and release documents.
2. Inventory all production modules.
3. Inventory all JSON, CSV, and Markdown outputs.
4. Map outputs to producer modules and current versions.
5. Identify required, optional, and context inputs.

### Phase 1B — Contract Design

1. Finalize plugin identity.
2. Finalize capability catalog.
3. Finalize input catalog.
4. Finalize report and artifact catalog.
5. Finalize schema-version declarations.
6. Finalize CIO presentation destinations.

### Phase 1C — Descriptive Implementation

1. Add manifest generator and static manifest output.
2. Add output-contract generator and static contract output.
3. Add read-only CIO presentation adapter metadata.
4. Add tests proving non-transformation and safety.

### Phase 1D — Freeze

1. Run compile validation.
2. Run targeted tests.
3. Run full Swing regression tests.
4. Verify no existing report format changed.
5. Create Milestone 1 freeze document.

## 17. Acceptance Criteria

Milestone 1 is complete when:

1. Trade-Swing-Bot is formally identifiable as a CIO strategy plugin.
2. The plugin manifest describes identity, version, capabilities, inputs, outputs, schemas, ownership, health, and safety.
3. The output contract catalogs every CIO-consumable Swing JSON, CSV, and Markdown artifact.
4. Existing Swing engines and calculations remain unchanged.
5. Existing report formats remain unchanged.
6. CIO-compatible presentation metadata is available without duplicating calculations.
7. No PostgreSQL code or dependency exists.
8. No Dividend Bot production code is changed.
9. The repositories remain separate.
10. All safety flags confirm paper-only, advisory-only, no brokerage execution, no order placement, and no capital movement.
11. Tests prove the compatibility layer is descriptive and non-transformative.

## 18. Permanent Decision Record

The Enterprise AI CIO will own future PostgreSQL imports and database persistence.

The Swing plugin will continue publishing JSON, CSV, and Markdown reports as its transparent audit and exchange formats.

Future PostgreSQL support will consume those outputs through a CIO-owned import layer. It will not require Swing engines to become database-aware.

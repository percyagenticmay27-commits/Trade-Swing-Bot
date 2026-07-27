# Swing CIO Artifact Inventory

## 1. Purpose

This document is the Milestone 1 Phase 9A inventory for registering Trade-Swing-Bot as a descriptive Enterprise AI CIO strategy plugin.

It catalogs the current Swing architecture and the JSON, CSV, Markdown, HTML, ZIP, and ledger-style artifacts that may be referenced by the future plugin manifest and output contract.

This inventory does not change any engine, calculation, public function, report field, CSV column, file path, or output format.

## 2. Permanent Boundaries

- Trade-Swing-Bot remains an independent repository.
- Trade-Dividend-Bot remains the Enterprise AI CIO host platform.
- Existing Swing engines remain the calculation owners.
- Existing reports remain the system-of-record exports for the current milestone.
- The CIO may discover, validate, link, and display Swing artifacts.
- The CIO must not reproduce Swing calculations.
- PostgreSQL is future AI CIO work and is excluded from this milestone.
- Swing engines must not connect directly to PostgreSQL.
- Paper-only and advisory-only operation is mandatory.

## 3. Safety Classification

The entire inventory inherits these mandatory declarations:

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

## 4. Inventory Status Definitions

- `FROZEN`: existing release/freeze documentation identifies the module as frozen.
- `IMPLEMENTED`: production module exists and publishes artifacts.
- `DESIGN_ONLY`: design exists but implementation is not established by this inventory.
- `OPTIONAL`: artifact may be absent without invalidating the complete Swing plugin.
- `REQUIRED_FOR_PLUGIN`: artifact is required for CIO plugin registration or validation.
- `CIO_CONSUMABLE`: the CIO may read or link the existing artifact without changing it.
- `INTERNAL_SUPPORT`: supports Swing processing but is not necessarily a dashboard report.

## 5. Architecture Inventory

### 5.1 Version 1.0 Reporting and Management Layer

| Module | Role | Status | Primary CIO destination |
|---|---|---|---|
| `stock_performance_report.py` | Position and ticker performance reporting | FROZEN | Performance and Weekly Review |
| `weekly_stock_report.py` | Weekly portfolio and ticker review | FROZEN | Performance and Weekly Review |
| `executive_dashboard.py` | High-level Swing executive summary | FROZEN with later awareness integrations | Swing Strategy Overview |
| `monthly_command_center.py` | Monthly management summary and review actions | FROZEN | Swing Strategy Overview |

### 5.2 Version 1.1 Intelligence Layer

| Module | Role | Status | Primary CIO destination |
|---|---|---|---|
| `market_intelligence_engine.py` | Company, sector, macro, rotation, and narrative intelligence | IMPLEMENTED | Market Intelligence |
| `market_regime_engine.py` | Market regime classification and support scoring | IMPLEMENTED | Market Intelligence |
| `momentum_score_engine.py` | Normalized opportunity momentum scoring | IMPLEMENTED | Opportunity Quality |

### 5.3 Version 1.2 Opportunity Quality Layer

| Module | Role | Status | Primary CIO destination |
|---|---|---|---|
| `opportunity_quality_engine.py` | Single source of truth for Opportunity Quality | FROZEN | Opportunity Quality |

Permanent Version 1.2 rules:

- Missing evidence equals zero.
- Entry Score is not part of Opportunity Quality.
- Entry Score is display-only within the Opportunity Quality module.
- QA and LIVE use identical calculations.
- Presentation mode must not change calculations.

### 5.4 Version 1.3 Position Intelligence Layer

| Module | Role | Status | Primary CIO destination |
|---|---|---|---|
| `strategy_assignment_engine.py` | Assigns Strategy A or Strategy B by ticker using rolling paper evidence | FROZEN / IMPLEMENTED | Strategy Assignment |
| `trade_lifecycle_manager.py` | Classifies paper-position lifecycle status | FROZEN / IMPLEMENTED | Position Lifecycle |
| `profit_protection_manager.py` | Classifies profit-protection and giveback review zones | FROZEN / IMPLEMENTED | Position Lifecycle |
| `reentry_manager.py` | Evaluates reentry-watch readiness | FROZEN / IMPLEMENTED | Reentry Review |
| `exit_review_manager.py` | Classifies positions requiring deeper exit review | FROZEN / IMPLEMENTED | Exit Review |
| `position_intelligence_engine.py` | Consolidates position-level advisory intelligence | FROZEN / IMPLEMENTED | Position Intelligence |

### 5.5 Version 1.4 Thesis Layer

| Module | Role | Status | Primary CIO destination |
|---|---|---|---|
| `thesis_monitor.py` | Evaluates whether the original research thesis remains intact | IMPLEMENTED | Thesis Monitor |

### 5.6 Historical Evidence Layer

| Module | Role | Status | Primary CIO destination |
|---|---|---|---|
| `historical_archive_manager.py` | Rolling history, annual archives, integrity, evidence retrieval, access logs, and retention planning | IMPLEMENTED | Historical Evidence and Archive Health |

## 6. Verified Published Artifact Families

### 6.1 Strategy Assignment

Producer:

```text
main/src/swing_trade_bot/strategy_assignment_engine.py
```

Output function:

```text
write_strategy_assignment_outputs(...)
```

Declared version:

```text
1.3
```

Artifacts:

| Artifact ID | Relative path | Format | Classification | CIO use |
|---|---|---|---|---|
| `strategy-assignments-csv` | `results/strategy_assignments.csv` | CSV | CIO_CONSUMABLE | Strategy table, filtering, future CIO import source |
| `strategy-assignments-json` | `results/strategy_assignments.json` | JSON | CIO_CONSUMABLE | Machine-readable strategy assignment payload |
| `strategy-assignments-md` | `results/strategy_assignments.md` | Markdown | CIO_CONSUMABLE | Human-readable report and audit output |

CSV columns:

```text
symbol
active_strategy
recommended_strategy
switch_eligible
confidence_level
review_window
cooldown_remaining_weeks
reason
strategy_a_return
strategy_b_return
strategy_a_max_drawdown
strategy_b_max_drawdown
strategy_a_win_rate
strategy_b_win_rate
strategy_a_trade_count
strategy_b_trade_count
```

JSON top-level fields:

```text
paper_trade_mode
version
assignments
```

Record identifier:

```text
symbol
```

Known enums:

```text
active_strategy / recommended_strategy:
- Strategy A
- Strategy B

confidence_level:
- warning
- review
- preferred
- high
- hold

review_window:
- 1_week
- 4_week
- 8_week
- 12_week
```

Missing-data behavior:

- Missing Strategy A or Strategy B evidence creates a hold-style assignment with zero-valued comparison evidence.
- One-week evidence is warning-only.
- Four weeks is the minimum review window.
- Eight weeks is preferred.
- Twelve weeks is high-confidence.
- A four-week default cooldown prevents rapid reassignment.

External schema declaration:

```text
strategy-assignments.v1.3
```

### 6.2 Thesis Monitor

Producer:

```text
main/src/swing_trade_bot/thesis_monitor.py
```

Output function:

```text
write_thesis_monitor_outputs(...)
```

Declared version:

```text
1.4
```

Artifacts:

| Artifact ID | Relative path | Format | Classification | CIO use |
|---|---|---|---|---|
| `thesis-monitor-json` | `results/thesis_monitor_report.json` | JSON | CIO_CONSUMABLE | Machine-readable thesis health and review actions |
| `thesis-monitor-md` | `results/thesis_monitor_report.md` | Markdown | CIO_CONSUMABLE | Human-readable thesis review report |

JSON top-level fields:

```text
paper_trade_mode
version
reviews
```

Review fields:

```text
symbol
active_strategy
thesis_state
thesis_health_score
thesis_intact
suggested_review_action
evidence_count
weak_evidence_count
original_thesis
reason
```

Record identifier:

```text
symbol
```

Known enums:

```text
thesis_state:
- strong
- intact
- weakening
- broken
- unknown

suggested_review_action:
- continue_research
- monitor_thesis
- review_thesis
- high_priority_review
- insufficient_evidence
```

Missing-data behavior:

- Fewer than the policy minimum evidence items produces `unknown`.
- Unknown thesis state produces `insufficient_evidence`.
- Missing optional evidence is excluded from the weighted denominator.
- No available weighted evidence produces a zero score.

External schema declaration:

```text
thesis-monitor.v1.4
```

### 6.3 Historical Archive Manager

Producer:

```text
main/src/swing_trade_bot/historical_archive_manager.py
```

Module version:

```text
1.0.0
```

Schema version:

```text
1.0
```

Default report artifacts:

| Artifact ID | Relative/default name | Format | Classification | CIO use |
|---|---|---|---|---|
| `archive-manager-json` | `archive_manager.json` | JSON | CIO_CONSUMABLE | Archive status, evidence inventory, integrity, and health |
| `archive-manager-md` | `archive_manager.md` | Markdown | CIO_CONSUMABLE | Human-readable archive report |
| `archive-manager-html` | `archive_manager.html` | HTML | OPTIONAL / CIO_LINKABLE | Existing human-readable archive presentation |
| `annual-history-zip` | `<archive_root>/<year>.zip` | ZIP | INTERNAL_SUPPORT / CIO_LINKABLE | Immutable annual historical package |
| `annual-manifest-json` | `manifest.json` inside annual ZIP | JSON | CIO_CONSUMABLE | Archive metadata and inventory |
| `archive-access-log` | Configured access-log path | JSON | INTERNAL_SUPPORT / CIO_CONSUMABLE | Read-only retrieval audit history |

Archive manifest fields include:

```text
archive_version
schema_version
archive_year
created_at_utc
file_count
stock_count
symbols
investment_count
lesson_count
policy_versions
market_era
date_range
```

Annual archive identifier:

```text
archive_year
```

Integrity fields include:

```text
archive_path
exists
readable
manifest_present
integrity_ok
checksum_sha256
errors
```

Retention rule:

```text
investor_approval_required_before_deletion: true
```

External schema declaration:

```text
historical-archive-manager.v1.0
```

## 7. Existing Report Families Requiring Field-Level Contract Extraction

The following existing report families are known parts of the Swing architecture. Their exact fields, columns, embedded versions, and paths must be extracted from their owning production files before the final machine-readable output contract is frozen.

| Report family | Expected formats | Current classification | CIO destination |
|---|---|---|---|
| Stock Performance Report | JSON, CSV, Markdown where currently implemented | CIO_CONSUMABLE | Performance and Weekly Review |
| Weekly Stock Report | JSON, CSV, Markdown where currently implemented | CIO_CONSUMABLE | Performance and Weekly Review |
| Executive Dashboard | JSON, Markdown | CIO_CONSUMABLE | Swing Strategy Overview |
| Monthly Command Center | JSON, Markdown | CIO_CONSUMABLE | Swing Strategy Overview |
| Portfolio Allocations | JSON, CSV where currently implemented | CIO_CONSUMABLE | Portfolio Risk and Allocation Recommendations |
| Portfolio Manager Report | CSV and related formats where currently implemented | CIO_CONSUMABLE | Portfolio Risk and Allocation Recommendations |
| Strategy Comparison | JSON | CIO_CONSUMABLE | Strategy Assignment |
| Strategy Recommendations | CSV | CIO_CONSUMABLE | Strategy Assignment |
| Confidence Report | JSON or CSV | OPTIONAL / CIO_CONSUMABLE | Watchlist and Discovery |
| Watchlist Report | JSON or CSV | OPTIONAL / CIO_CONSUMABLE | Watchlist and Discovery |
| Earnings Report | JSON or CSV | OPTIONAL / CIO_CONSUMABLE | Risk and Event Review |
| Theme Momentum | JSON | OPTIONAL / CIO_CONSUMABLE | Watchlist and Discovery |
| Source Confluence | JSON | OPTIONAL / CIO_CONSUMABLE | Watchlist and Discovery |
| Market Intelligence | JSON, Markdown | CIO_CONSUMABLE | Market Intelligence |
| Market Regime | JSON, Markdown | CIO_CONSUMABLE | Market Intelligence |
| Momentum Scores | JSON, Markdown | CIO_CONSUMABLE | Opportunity Quality |
| Opportunity Quality | JSON, CSV, Markdown where currently implemented | CIO_CONSUMABLE | Opportunity Quality |
| Trade Lifecycle | Existing published formats | CIO_CONSUMABLE | Position Lifecycle |
| Profit Protection | Existing published formats | CIO_CONSUMABLE | Position Lifecycle |
| Reentry Review | Existing published formats | CIO_CONSUMABLE | Reentry Review |
| Exit Review | Existing published formats | CIO_CONSUMABLE | Exit Review |
| Position Intelligence | Existing published formats | CIO_CONSUMABLE | Position Intelligence |

This section is intentionally non-transformative. The final output contract must use the actual existing paths and schemas found in production modules; it must not create replacement schemas for these reports.

## 8. Required CIO Plugin Artifacts To Be Added

These are new descriptive compatibility artifacts. They do not replace current Swing reports.

| Artifact | Planned path | Purpose | Required status |
|---|---|---|---|
| Swing CIO Plugin Manifest | `main/configs/swing_cio_plugin_manifest.json` | Plugin identity, capabilities, inputs, published reports, safety, and registration metadata | REQUIRED_FOR_PLUGIN |
| Swing CIO Output Contract | `main/configs/swing_cio_output_contract.json` | Machine-readable catalog of CIO-consumable Swing artifacts | REQUIRED_FOR_PLUGIN |
| Manifest builder/validator | `main/src/swing_trade_bot/swing_cio_plugin_manifest.py` | Build and validate descriptive manifest | REQUIRED_FOR_PLUGIN |
| Output contract builder/validator | `main/src/swing_trade_bot/swing_cio_output_contract.py` | Build and validate descriptive output contract | REQUIRED_FOR_PLUGIN |
| CIO presentation adapter | `main/src/swing_trade_bot/swing_cio_presentation_adapter.py` | Map existing artifact metadata to CIO UI conventions without calculations | REQUIRED_FOR_PLUGIN |
| Manifest tests | `main/tests/test_swing_cio_plugin_manifest.py` | Validate identity, safety, and capability contract | REQUIRED_FOR_PLUGIN |
| Output contract tests | `main/tests/test_swing_cio_output_contract.py` | Validate artifact ownership, versions, paths, and formats | REQUIRED_FOR_PLUGIN |
| Presentation adapter tests | `main/tests/test_swing_cio_presentation_adapter.py` | Prove the adapter is display-only | REQUIRED_FOR_PLUGIN |

## 9. CIO Presentation Map

| CIO page | Source artifact families | Calculation owner |
|---|---|---|
| Swing Strategy Overview | Executive Dashboard, Monthly Command Center, plugin manifest | Existing Swing reporting modules |
| Watchlist and Discovery | Watchlist, Theme Momentum, Source Confluence, Confidence | Existing discovery and watchlist modules |
| Market Intelligence | Market Intelligence, Market Regime | Existing intelligence engines |
| Opportunity Quality | Opportunity Quality, Momentum Scores, Entry display metadata | Existing opportunity and entry engines |
| Portfolio Risk and Allocation Recommendations | Portfolio Allocation and Portfolio Manager reports | Existing risk and allocation modules |
| Position Lifecycle | Trade Lifecycle and Profit Protection | Existing Version 1.3 managers |
| Reentry Review | Reentry Manager outputs | Reentry Manager |
| Exit Review | Exit Review outputs | Exit Review Manager |
| Strategy Assignment | Strategy Assignments and comparison evidence | Strategy Assignment Engine |
| Thesis Monitor | Thesis Monitor Report | Thesis Monitor |
| Position Intelligence | Position Intelligence outputs | Position Intelligence Engine |
| Performance and Weekly Review | Stock Performance and Weekly Stock reports | Existing reporting modules |
| Historical Evidence and Archive Health | Archive Manager, manifests, integrity, access log | Historical Archive Manager |

## 10. Missing-Artifact Rules For CIO Registration

1. Missing required plugin artifacts are registration errors.
2. Missing required Swing reports are surfaced according to the existing owning module's rules.
3. Missing optional reports create warnings, not plugin-registration failure.
4. The CIO must not fabricate missing reports.
5. The presentation adapter may provide an empty-state message but may not produce substitute calculations.
6. Malformed JSON or incompatible CSV headers must be reported as validation errors.
7. A report schema mismatch must not trigger automatic transformation during Milestone 1.
8. Historical archive deletion always requires investor approval.

## 11. Schema Version Rules

- Existing embedded versions remain authoritative for their artifacts.
- External contract versions describe existing payloads without changing them.
- JSON and CSV artifacts intended for CIO consumption require a declared schema version.
- Markdown reports require a layout/report version in the output contract.
- HTML and ZIP artifacts may be linked or indexed but are not replacements for JSON/CSV contract data.
- A breaking field, type, enum, or column change requires a major schema-version increase.
- Backward-compatible additive metadata may use a minor increase.
- No report is rewritten solely to insert schema metadata.

## 12. Phase 9A Completion Criteria

Phase 9A is complete when:

- all production modules have been enumerated
- every published artifact has a producer owner
- every CIO-consumable artifact has a known path and format
- required and optional artifacts are distinguished
- known embedded versions are recorded
- missing-data behavior is recorded
- CIO presentation destinations are assigned
- no engine or report schema has been changed

This inventory establishes the initial catalog and fully verifies the Strategy Assignment, Thesis Monitor, and Historical Archive artifact families. Field-level extraction for the remaining existing report families is the next inventory refinement before the machine-readable output contract is frozen.

## 13. Next Development Step

Proceed to Phase 9B in this order:

1. Extract exact fields and paths from remaining report-producing modules.
2. Create `main/configs/swing_cio_plugin_manifest.json`.
3. Create the manifest builder and validator.
4. Add manifest unit tests.
5. Create the machine-readable output contract only after remaining field-level extraction is complete.

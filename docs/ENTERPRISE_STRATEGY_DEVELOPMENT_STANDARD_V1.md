# Enterprise Strategy Development Standard V1

**Version:** 1.0  
**Status:** Frozen for Stage 1

## 1. Purpose

This standard defines how every present and future strategy plugin must be designed, implemented, tested, and operated within the Enterprise Trade Platform.

## 2. Scope

It applies to Dividend, Swing, Options, Futures, Crypto, REIT, Income, and all future strategies. It also applies when converting an existing standalone bot into an Enterprise-compatible plugin.

## 3. Core Principles

Every strategy must be:

- contract-driven;
- independently runnable;
- modular;
- paper-only by default;
- service-oriented;
- observable through status, health, outputs, and events;
- compatible with AI CIO discovery and monitoring.

## 4. Ownership Boundary

A strategy owns only:

- discovery and screening rules unique to the strategy;
- analysis and scoring unique to the strategy;
- entry, exit, lifecycle, and recommendation logic unique to the strategy;
- strategy-specific paper state;
- strategy-specific reports and evidence.

A strategy does not own provider selection, shared market-data retrieval, shared cache, scheduling, notifications, enterprise portfolio authority, governance, plugin registration, contract validation, or enterprise dashboards.

## 5. Required Logical Components

Every strategy must expose clear components for:

1. discovery;
2. analysis;
3. scoring;
4. paper decision logic;
5. state management;
6. report generation;
7. status publication;
8. health publication;
9. output registration;
10. manifest publication.

These components may be implemented in separate modules or grouped where appropriate, but their responsibilities must remain distinct and testable.

## 6. Required Contracts

Every strategy must publish:

- `manifest.json`: stable identity, version, capabilities, dependencies, permissions, entrypoint, contracts, outputs, and state ownership;
- `status.json`: current lifecycle and runtime condition;
- `health.json`: diagnostics, warnings, errors, dependencies, and readiness;
- `outputs.json`: registered reports, data files, logs, and latest output references.

Contract files must use UTF-8 JSON, deterministic field names, semantic versions, and ISO-8601 UTC timestamps.

## 7. Identity

Each strategy must define a stable, unique `strategy_id`. Renaming a display name must not change the identifier. IDs must not be reused after retirement. Recommended format:

```text
STRATEGY-<DOMAIN>-<NUMBER>
```

Examples: `STRATEGY-DIVIDEND-001`, `STRATEGY-SWING-001`.

## 8. Enterprise Service Access

Strategies consume Enterprise APIs instead of infrastructure implementations. Market data must come only from the Enterprise Market Data API. Portfolio changes must be requests to the Portfolio Service and remain subject to Governance. Notifications must be events or requests to the Notification Service. Scheduling must be declared, not privately installed through cron or another scheduler.

## 9. Independent Runtime

A strategy must support an independently runnable paper cycle for local tests, recovery, and diagnosis. Independent execution must not bypass Enterprise contracts or create a second provider, scheduler, notification, or portfolio implementation.

## 10. State Rules

Strategy-specific paper state is owned by the strategy. Enterprise allocation, cross-strategy cash, provider cache, and enterprise governance state are not strategy-owned. State writes must be atomic where practical, recoverable, versioned when schemas change, and registered in `outputs.json` or the manifest.

## 11. Events

Strategies publish standardized Enterprise events for material lifecycle, run, health, output, allocation-request, and failure changes. Strategies must not rely on undocumented direct imports or hidden callback chains.

## 12. Error and Missing-Evidence Rules

- Missing required inputs produce an error and a non-success status.
- Missing optional inputs produce warnings and documented fallback behavior.
- Missing evidence is never fabricated.
- Partial results must be marked partial or degraded.
- A failed notification must not rewrite a successful analysis as failed, but it must appear in health and event records.

## 13. Testing Requirements

Every strategy must include:

- unit tests for strategy logic;
- contract-schema tests;
- manifest validation tests;
- status and health tests;
- output-registration tests;
- Enterprise API boundary tests;
- compatibility tests;
- paper-only safety tests;
- empty, missing, malformed, and partial-input tests;
- deterministic tests for scoring and decisions.

## 14. Certification

A strategy advances through Prototype, Development, Unit Tested, Contract Validated, Paper Certified, Enterprise Certified, and Production Paper. AI CIO allocation eligibility requires the certification level defined by Governance.

## 15. Versioning

Strategy versions follow semantic versioning. Contract-breaking changes require a major version. New compatible features require a minor version. Compatible fixes require a patch version. Enterprise API and strategy versions remain independently versioned.

## 16. Prohibited Design

A strategy must never:

- place real orders;
- enable broker execution;
- manage brokerage accounts;
- move money;
- call providers directly;
- select providers;
- maintain a competing shared cache;
- create a private scheduler;
- send notifications directly when Enterprise Notification Service is available;
- claim ownership of enterprise cash;
- bypass Governance;
- import AI CIO internals for recognition;
- silently change frozen public schemas.

## 17. Required AI Instruction

All AI-assisted work must begin with:

```text
Read docs/README_FOR_AI_DEVELOPERS.md before doing anything. Follow every mandatory Enterprise standard. Implement only strategy-specific logic. Do not duplicate or bypass Enterprise Core. Preserve paper-only operation and all required contracts and tests.
```

## 18. Definition of Done

Development is complete only when the strategy is independently runnable, contract-valid, compatible with the declared Enterprise version, observable by AI CIO, paper certified, tested, documented, and free of prohibited infrastructure duplication.

# Enterprise Compatibility Matrix V1

**Version:** 1.0  
**Status:** Frozen for Stage 1

## 1. Purpose

Define the minimum compatibility rules between Enterprise Core, AI CIO, the Enterprise SDK, public APIs, contracts, and strategy plugins.

## 2. Version Streams

Each component is independently versioned:

- Enterprise Core
- AI CIO
- Enterprise SDK
- Enterprise APIs
- Plugin Specification
- Strategy contracts
- Event Specification
- Individual strategies
- Provider adapters

## 3. V1 Baseline Matrix

| Component | Required/Supported Version | Rule |
|---|---:|---|
| Enterprise Architecture | 1.x | Required and frozen for Stage 1 |
| Plugin Specification | 1.x | Required for all strategy plugins |
| AI CIO Integration Standard | 1.x | Required for discovery and monitoring |
| Strategy Development Standard | 1.x | Required for new and migrated strategies |
| Enterprise SDK | 1.x | Required once implemented; compatible manual contracts allowed during migration |
| Market Data API | 1.x | Required for strategies consuming market data |
| Portfolio API | 1.x | Required for allocation-aware strategies |
| Governance API | 1.x | Required for allocation or policy decisions |
| Reporting API | 1.x | Required for enterprise report registration |
| Notification API | 1.x | Optional unless notifications are declared |
| Event Specification | 1.x | Required for Enterprise events |
| Contract Validation | 1.x | Required for registration |
| Strategy Contract Version | 1.x | Required for manifest, status, health, and outputs |

## 4. Semantic Version Rules

- Patch changes are compatible fixes.
- Minor changes may add optional fields or capabilities and must remain backward compatible within the same major version.
- Major changes may break compatibility and require explicit migration.

## 5. Compatibility Decision

A strategy is:

- `COMPATIBLE` when every required major version is supported;
- `COMPATIBLE_WITH_WARNINGS` when only optional features or deprecated compatible versions are involved;
- `INCOMPATIBLE` when a required major version, contract, safety rule, or service is unsupported.

## 6. Contract Evolution

Consumers must ignore unknown optional fields. Required fields cannot be removed or redefined within major version 1. New required fields require either a new major contract version or an explicitly versioned migration period.

## 7. SDK Independence During Migration

Before the SDK is implemented, a strategy may publish compliant contracts directly. This temporary path does not permit custom schemas or bypass validation. After SDK adoption is declared mandatory, the compatibility matrix must be updated in a later version.

## 8. Provider Adapter Compatibility

Strategies never declare provider-adapter compatibility because providers are hidden behind the Market Data API. Enterprise Core alone validates Yahoo, Robinhood read-only, cache, and future provider adapters.

## 9. AI CIO Compatibility

AI CIO recognizes a strategy only when contract, event, API, and safety versions are compatible. AI CIO must not compensate for incompatibility by importing or patching private strategy code.

## 10. Deprecation

A compatible version must be marked deprecated before removal. Deprecation notices must identify the replacement, migration path, and final supported release. Stage 1 does not authorize any V1 removal.

## 11. Acceptance Criteria

Every registered strategy has a recorded compatibility result, and incompatible major versions or missing required services block registration or trigger quarantine.

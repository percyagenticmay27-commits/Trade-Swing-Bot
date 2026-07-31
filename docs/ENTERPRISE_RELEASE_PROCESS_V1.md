# Enterprise Release Process V1

**Version:** 1.0  
**Status:** Frozen for Stage 1

## 1. Purpose

Define the promotion, certification, release, rollback, and archival process for Enterprise strategy plugins.

## 2. Promotion Lifecycle

Every strategy progresses through:

1. `PROTOTYPE`
2. `DEVELOPMENT`
3. `UNIT_TESTED`
4. `CONTRACT_VALIDATED`
5. `PAPER_CERTIFIED`
6. `ENTERPRISE_CERTIFIED`
7. `PRODUCTION_PAPER`
8. `MAINTENANCE`
9. `DEPRECATED`
10. `ARCHIVED`

A strategy may not skip required certification stages.

## 3. Prototype

Purpose and strategy boundaries are documented. Prototype outputs are experimental and not eligible for AI CIO allocation.

## 4. Development

Strategy-specific logic, state, contracts, and tests are implemented. Enterprise Core functionality must not be duplicated.

## 5. Unit Tested

All strategy unit tests and malformed, missing, empty, boundary, and deterministic cases pass. Failures block promotion.

## 6. Contract Validated

`manifest.json`, `status.json`, `health.json`, and `outputs.json` pass the Enterprise Contract Validation Standard. Compatibility and safety checks must pass.

## 7. Paper Certified

The strategy completes representative paper cycles, preserves all paper-only rules, generates registered outputs, recovers safely from missing dependencies, and demonstrates consistent state handling.

## 8. Enterprise Certified

The strategy is registered by AI CIO, publishes valid events and heartbeats, uses Enterprise APIs, passes compatibility checks, and has no prohibited direct provider or broker dependency.

## 9. Production Paper

The strategy may run under the Enterprise Scheduler and be monitored by AI CIO. Production Paper does not permit real trading or broker execution.

## 10. Release Package

Each release must include:

- semantic version;
- release notes;
- validated contracts;
- passing test summary;
- compatibility result;
- paper-certification evidence;
- migration notes for state or schema changes;
- rollback instructions;
- known warnings and limitations.

## 11. Approval Gates

Promotion requires evidence from the prior stage. Blocking contract, compatibility, safety, governance, or test errors prevent release. Warnings require explicit documented acceptance.

## 12. Rollback

A release must support rollback to the last known compatible Production Paper version. State migrations must be reversible or backed up. Rollback must preserve audit history and strategy identity.

## 13. Emergency Quarantine

AI CIO or Governance may quarantine a strategy for safety failure, incompatible contracts, corrupt state, repeated critical health failure, or prohibited direct execution behavior. Quarantine stops scheduling and allocation eligibility but preserves evidence.

## 14. Maintenance and Deprecation

Maintenance releases preserve public V1 contracts unless versioned otherwise. Deprecation must identify replacement, migration plan, and support period. Archived IDs and history remain reserved.

## 15. V1 Safety Rule

All lifecycle stages remain paper-only. No release stage authorizes real orders, broker execution, account management, or capital movement.

## 16. Acceptance Criteria

A strategy reaches Production Paper only through documented gates with passing tests, valid contracts, compatible versions, paper certification, AI CIO registration, and rollback evidence.

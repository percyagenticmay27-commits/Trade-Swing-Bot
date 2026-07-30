# Enterprise Contract Validation Standard V1

**Version:** 1.0  
**Status:** Frozen for Stage 1

## 1. Purpose

Define the validation required before a strategy can be recognized, registered, monitored, scheduled, or considered for AI CIO allocation.

## 2. Required Contracts

Validation covers:

- `manifest.json`
- `status.json`
- `health.json`
- `outputs.json`

## 3. Validation Sequence

1. Confirm required files exist.
2. Confirm UTF-8 JSON parses successfully.
3. Validate schema and contract versions.
4. Validate stable strategy identity.
5. Validate lifecycle and certification values.
6. Validate capabilities and required services.
7. Validate permissions and least privilege.
8. Validate entrypoint, state, and output declarations.
9. Validate compatibility with Enterprise API and SDK versions.
10. Validate paper-only safety declarations and runtime evidence.
11. Validate required tests and certification evidence.
12. Produce a deterministic validation report.

## 4. Manifest Requirements

The manifest must include:

- `strategy_id`
- `strategy_name`
- `strategy_type`
- `version`
- `schema_version`
- `contract_version`
- `lifecycle_status`
- `certification_level`
- `paper_trade_mode`
- `live_trading_enabled`
- `broker_execution_enabled`
- `entrypoint`
- `capabilities`
- `required_enterprise_services`
- `permissions`
- `contracts`
- `outputs`
- `state_ownership`

## 5. Status Requirements

Status must identify the strategy, current runtime state, latest cycle, latest successful run, latest failure, timestamps, warnings, and error summary.

## 6. Health Requirements

Health must report overall status, checks, dependencies, missing required files, warnings, errors, last heartbeat, and readiness. Allowed overall values are `OK`, `WARNING`, `ERROR`, and `UNKNOWN`.

## 7. Outputs Requirements

Outputs must enumerate registered JSON, CSV, Markdown, log, and data artifacts as applicable; latest output references; output count; missing outputs; warnings; and generated timestamp.

## 8. Safety Validation

Registration must fail when any of the following is true:

- `paper_trade_mode` is not `true`;
- `live_trading_enabled` is not `false`;
- `broker_execution_enabled` is not `false`;
- code or configuration exposes real-order execution;
- the strategy directly calls a market-data provider;
- the strategy bypasses Governance or Enterprise portfolio authority.

## 9. Severity and Outcome

Validation findings use `INFO`, `WARNING`, and `ERROR`.

Outcomes:

- `VALID`: no errors;
- `VALID_WITH_WARNINGS`: no errors and one or more warnings;
- `INVALID`: one or more errors.

Only `VALID` and policy-approved `VALID_WITH_WARNINGS` strategies may register. Allocation eligibility may require `VALID`.

## 10. Validation Report

The report must include strategy ID, validator version, timestamp, outcome, checks performed, findings, compatibility result, safety result, and remediation instructions.

## 11. Revalidation

Revalidation is required after manifest changes, major or minor strategy version changes, Enterprise API compatibility changes, permission changes, state-schema changes, failed safety checks, or certification promotion.

## 12. No Silent Repair

The validator must not silently edit strategy contracts. It may recommend exact corrections, but the strategy owner must publish the corrected contract.

## 13. Acceptance Criteria

A validator implementing this standard can deterministically accept or reject any strategy using published contracts and evidence without inspecting private strategy logic for discovery.

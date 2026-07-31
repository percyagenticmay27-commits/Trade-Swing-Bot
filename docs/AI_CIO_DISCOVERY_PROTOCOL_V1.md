# AI CIO Discovery Protocol V1

**Version:** 1.0  
**Status:** Frozen for Stage 1

## 1. Purpose

Define how AI CIO discovers, validates, recognizes, registers, and monitors a strategy without importing the strategy's private implementation.

## 2. Discovery Source

AI CIO discovers a strategy through its published `manifest.json` and companion contracts. Repository names, folder names, Python imports, display names, and informal prompts are not authoritative identity sources.

## 3. Required Discovery Workflow

1. Strategy publishes `manifest.json`, `status.json`, `health.json`, and `outputs.json`.
2. Strategy performs local contract validation.
3. Discovery Service finds the declared contract location.
4. Contract Validator validates identity, schemas, permissions, services, compatibility, and paper-only safety.
5. AI CIO checks that `strategy_id` is unique and stable.
6. Plugin Registry records the strategy and contract versions.
7. AI CIO publishes `PluginRegistered` or a rejection event.
8. Health Monitor begins consuming heartbeats and health updates.
9. Scheduler may activate only declared and approved schedules.
10. AI CIO displays the strategy according to lifecycle and certification level.

## 4. Recognition Record

The registry record must contain:

- strategy ID and name;
- strategy type;
- version;
- contract and schema versions;
- lifecycle status;
- certification level;
- capabilities;
- required Enterprise services;
- permissions;
- entrypoint;
- contract locations;
- output and state declarations;
- latest validation outcome;
- latest heartbeat and health;
- registration timestamp.

## 5. Registration Outcomes

- `REGISTERED`: all required checks pass.
- `REGISTERED_WITH_WARNINGS`: allowed only by policy and not automatically allocation-eligible.
- `REJECTED`: one or more blocking errors.
- `QUARANTINED`: previously registered strategy now violates safety, compatibility, or integrity requirements.

## 6. Duplicate Identity

A duplicate `strategy_id` is a blocking error. A renamed strategy retains its original ID. A replacement strategy must use a new ID unless it is a versioned continuation approved under the release process.

## 7. Heartbeat and Health Monitoring

Registered strategies publish heartbeats with runtime status, cycle ID, contract versions, and health summary. Missing heartbeats transition health according to policy but do not authorize AI CIO to rewrite strategy state.

## 8. Lifecycle Changes

Lifecycle and certification changes require updated contracts and revalidation. AI CIO records transitions and publishes events. Unsupported or invalid transitions are rejected.

## 9. Removal and Archival

A strategy may be disabled, deprecated, or archived without deleting historical registry records. Archived IDs cannot be reassigned.

## 10. Security and Boundaries

Discovery grants no broker access, provider access, filesystem access beyond declared contracts, or permission beyond the manifest and Enterprise policy. AI CIO must not execute arbitrary strategy code merely to determine identity.

## 11. Failure Handling

A rejected strategy receives a structured validation report. Discovery retries must not create duplicate registrations. Previously valid strategies with expired compatibility or failed safety checks are quarantined until corrected and revalidated.

## 12. Acceptance Criteria

A newly published compliant strategy can become registered and monitored using contracts alone, while an incompatible, unsafe, malformed, or duplicate strategy is deterministically rejected or quarantined.

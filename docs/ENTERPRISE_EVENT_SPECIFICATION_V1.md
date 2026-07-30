# Enterprise Event Specification V1

**Version:** 1.0  
**Status:** Frozen for Stage 1

## 1. Purpose

Standardize event communication between strategies, Enterprise Core, and AI CIO.

## 2. Event Envelope

Every event must contain:

```json
{
  "event_id": "UUID",
  "event_type": "StrategyCycleCompleted",
  "event_version": "1.0.0",
  "occurred_at": "ISO-8601 UTC",
  "producer_id": "STRATEGY-SWING-001",
  "producer_type": "STRATEGY",
  "correlation_id": "UUID",
  "cycle_id": "string-or-null",
  "severity": "INFO",
  "paper_trade_mode": true,
  "payload": {}
}
```

## 3. Required Event Types

Lifecycle:

- `PluginDiscovered`
- `PluginValidated`
- `PluginRegistered`
- `StrategyStarted`
- `StrategyPaused`
- `StrategyStopped`
- `StrategyFailed`

Run:

- `StrategyCycleStarted`
- `StrategyCycleCompleted`
- `StrategyCycleFailed`
- `OutputsPublished`

Health:

- `StrategyHealthChanged`
- `HeartbeatPublished`
- `DependencyUnavailable`
- `DependencyRecovered`

Portfolio and governance:

- `PortfolioAllocationRequested`
- `PortfolioAllocationApproved`
- `PortfolioAllocationRejected`
- `GovernanceReviewRequired`

Enterprise operations:

- `MarketDataUpdated`
- `DailyCycleCompleted`
- `WeeklyReviewCompleted`
- `MonthlyReviewCompleted`

## 4. Severity

Allowed values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

## 5. Delivery Rules

Events are immutable after publication. Consumers must be idempotent using `event_id`. Retries must preserve the original event ID. Ordering is guaranteed only within a producer and cycle where the transport supports it.

## 6. Payload Rules

Payloads must be JSON-compatible, versioned when structure changes, minimal, and free of secrets. Large reports are referenced by registered output path or URI rather than embedded.

## 7. Error Handling

Failure to publish an event must be recorded in health and status. Event failure must not silently erase a completed strategy result. Critical lifecycle and failure events must be retried according to Enterprise policy.

## 8. Compatibility

Adding optional payload fields is backward compatible. Removing or redefining required fields requires a new major event version. Consumers must ignore unknown optional fields.

## 9. Prohibited Use

Events must not be used to place real orders, transmit credentials, bypass Governance, mutate another strategy's private state, or conceal direct provider dependencies.

## 10. Acceptance Criteria

A compliant strategy can publish lifecycle, cycle, health, output, and allocation-request events using the common envelope, and AI CIO can correlate them without importing strategy code.

# Enterprise SDK Specification V1

**Version:** 1.0  
**Status:** Frozen design for Stage 1

## 1. Purpose

Define the minimum SDK contract that allows every strategy to interact with Enterprise Core and the AI CIO consistently without duplicating infrastructure.

## 2. SDK Responsibilities

The SDK will provide helpers for:

- manifest creation and validation;
- status publication;
- health publication;
- output registration;
- event publication;
- Enterprise API clients;
- startup and shutdown lifecycle hooks;
- heartbeat publication;
- compatibility checks;
- paper-only safety assertions.

The SDK does not implement strategy calculations.

## 3. Conceptual Base Interface

```python
class StrategyPlugin:
    def build_manifest(self): ...
    def validate_contracts(self): ...
    def start(self): ...
    def run_cycle(self): ...
    def publish_status(self): ...
    def publish_health(self): ...
    def publish_outputs(self): ...
    def publish_event(self, event): ...
    def stop(self): ...
```

Concrete names may change during implementation only if the public V1 contract is updated before freeze. Strategy logic must remain separate from SDK plumbing.

## 4. Required SDK Modules

- `identity`: stable IDs and version metadata;
- `contracts`: JSON contract builders and validators;
- `lifecycle`: startup, heartbeat, run, pause, stop, and failure transitions;
- `events`: event envelopes and publishers;
- `clients.market_data`: Enterprise Market Data API client;
- `clients.portfolio`: allocation and portfolio request client;
- `clients.governance`: policy and approval client;
- `clients.reporting`: enterprise report registration client;
- `clients.notifications`: notification request client;
- `compatibility`: API and SDK compatibility checks;
- `safety`: paper-only enforcement;
- `testing`: reusable contract and compatibility fixtures.

## 5. Contract Publication

The SDK must write deterministic UTF-8 JSON, include schema and contract versions, use ISO-8601 UTC timestamps, and support atomic replacement. Publication failures must surface in health and status.

## 6. Enterprise API Clients

SDK clients hide transport details from strategies. They return normalized contracts and structured errors. Strategies must not import provider adapters or AI CIO internals.

## 7. Lifecycle Hooks

Required transitions:

```text
INSTALLED -> REGISTERED -> VALIDATED -> RUNNING -> PAUSED/STOPPED
                                  \-> DEGRADED/ERROR
```

The SDK must reject invalid transitions and preserve the prior valid state with an error record.

## 8. Heartbeats

A heartbeat includes strategy ID, runtime status, timestamp, current cycle ID, contract versions, and health summary. Heartbeats must not contain secrets or broker credentials.

## 9. Safety

The SDK must expose a mandatory assertion equivalent to:

```text
paper_trade_mode=True
live_trading_enabled=False
broker_execution_enabled=False
```

A strategy failing safety validation cannot register as Enterprise Certified or Production Paper.

## 10. Backward Compatibility

Minor SDK releases must remain backward compatible within major version 1. Breaking changes require SDK major version 2 and an updated compatibility matrix.

## 11. Error Model

SDK errors must include code, message, severity, retryability, component, timestamp, and optional evidence. Secrets and raw credentials must never be included.

## 12. Testing Support

The SDK must provide reusable tests for contract presence, schema validity, lifecycle transitions, event envelopes, output registration, API boundaries, and paper-only restrictions.

## 13. V1 Non-Goals

V1 does not define broker execution, real-money workflows, autonomous code modification, provider-specific strategy access, or dynamic remote code loading.

## 14. Acceptance Criteria

The SDK design is satisfied when a new strategy can publish all required contracts, self-validate, communicate through Enterprise APIs, publish events and heartbeats, remain independently runnable, and be recognized by AI CIO without custom integration code.

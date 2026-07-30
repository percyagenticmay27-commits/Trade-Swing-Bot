# README for AI Developers

**Version:** 1.0  
**Status:** Stage 1 Frozen Entry Point

## Mandatory First Instruction

Read this document before designing, generating, modifying, testing, or deploying any strategy, bot, plugin, or Enterprise service.

## Purpose

This is the single entry point for every AI assistant, coding agent, and developer working in the Enterprise Trade Platform ecosystem. It establishes the required reading order and the permanent rules that protect interoperability with Enterprise Core and the AI CIO.

## Required Reading Order

1. `STAGE_1_ENTERPRISE_ARCHITECTURE_FREEZE.md`
2. `ENTERPRISE_DOMAIN_ARCHITECTURE.md`
3. `ENTERPRISE_LAYER_ARCHITECTURE.md`
4. `ENTERPRISE_SERVICE_CATALOG.md`
5. `ENTERPRISE_API_CONTRACTS.md`
6. `MARKET_PROVIDER_ARCHITECTURE.md`
7. `MARKET_PROVIDER_CAPABILITY_MATRIX.md`
8. `PLUGIN_SPECIFICATION_V1.md`
9. `AI_CIO_STRATEGY_INTEGRATION_STANDARD_V1.md`
10. `ENTERPRISE_STRATEGY_DEVELOPMENT_STANDARD_V1.md`
11. `ENTERPRISE_SDK_SPECIFICATION_V1.md`
12. `ENTERPRISE_EVENT_SPECIFICATION_V1.md`
13. `ENTERPRISE_CONTRACT_VALIDATION_STANDARD_V1.md`
14. `AI_CIO_DISCOVERY_PROTOCOL_V1.md`
15. `ENTERPRISE_COMPATIBILITY_MATRIX_V1.md`
16. `ENTERPRISE_RELEASE_PROCESS_V1.md`
17. `ENTERPRISE_CAPABILITY_REGISTRY.md`
18. `DATA_OWNERSHIP_MATRIX.md`
19. `ENTERPRISE_DATA_FLOW.md`
20. `REPOSITORY_DEPENDENCY_GRAPH.md`
21. `MIGRATION_PLAN_V1.md`

Documents that do not yet exist in a strategy repository must be obtained from the authoritative Enterprise Platform documentation set before integration begins.

## Permanent Ownership Rules

Enterprise Core owns shared infrastructure, including market data, provider selection, normalization, validation, cache, portfolio services, governance, scheduler, notifications, enterprise reporting, plugin registration, contract validation, health monitoring, configuration, and shared logging.

The AI CIO owns cross-strategy monitoring, enterprise analytics, recommendations, executive dashboards, and capital-allocation decisions.

A strategy plugin owns only strategy-specific business logic, strategy-specific state, and strategy-specific reports.

## Required Strategy Contracts

Every strategy must publish and maintain:

- `manifest.json`
- `status.json`
- `health.json`
- `outputs.json`

The AI CIO recognizes strategies through these contracts. It must not import private strategy modules to discover or identify them.

## Non-Negotiable Rules

- Preserve `paper_trade_mode=True`.
- Do not place real orders.
- Do not enable broker execution.
- Do not move capital.
- Do not manage brokerage accounts.
- Do not call Yahoo, Robinhood, Codex, Robinhood MCP, or any provider directly from a strategy.
- Obtain market data only through the Enterprise Market Data API.
- Do not duplicate Enterprise scheduler, cache, notification, reporting, portfolio, governance, registration, or provider logic.
- Keep each strategy independently runnable for local validation and recovery.
- Missing evidence must never be silently invented.

## Master Development Command

```text
You are building or modifying a strategy plugin for the Enterprise Trade Platform.

Before generating architecture, code, tests, reports, configuration, or documentation, read docs/README_FOR_AI_DEVELOPERS.md and every mandatory document listed in its Required Reading Order. Treat the frozen Enterprise documents as the single source of truth.

Do not redesign, duplicate, or bypass Enterprise Core. Implement only strategy-specific business logic and strategy-owned state.

Publish and validate manifest.json, status.json, health.json, and outputs.json. Declare a stable strategy ID, strategy name, semantic version, lifecycle status, certification level, capabilities, permissions, required Enterprise services, entrypoint, output paths, and state ownership.

Consume market data only through the Enterprise Market Data API. Never call Yahoo, Robinhood, Codex, Robinhood MCP, provider adapters, or shared cache directly. Strategies must remain unaware of which provider supplied normalized data.

Use Enterprise services for portfolio requests, governance, scheduling, notifications, registration, health monitoring, and enterprise reporting. Publish events instead of creating hidden cross-module dependencies.

Remain independently runnable and preserve paper_trade_mode=True. No brokerage execution, real orders, account management, capital movement, or trading API calls are permitted.

Include unit tests, contract tests, health/status tests, compatibility tests, and paper-certification tests. If a requested feature belongs to Enterprise Core, stop and identify the correct Enterprise owner instead of duplicating the feature inside the strategy.
```

## Completion Checklist

A strategy is ready to request AI CIO registration only when:

- all mandatory documents were reviewed;
- ownership boundaries are respected;
- required contracts exist and validate;
- service and permission declarations are complete;
- tests pass;
- paper-only restrictions pass static and runtime checks;
- compatibility requirements pass;
- strategy outputs and state paths are registered;
- the strategy can start, report health, complete a paper cycle, and stop cleanly.

This document is the required first reference for all future bots and strategies.

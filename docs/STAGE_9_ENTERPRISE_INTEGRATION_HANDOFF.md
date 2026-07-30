# Stage 9 Enterprise Integration Handoff

**Target repository:** `percyagenticmay27-commits/Trade-Swing-Bot`  
**Enterprise Core repository:** `percyagenticmay27-commits/Trade-Dividend-Bot`  
**Stage 9 branch:** `stage-9-enterprise-integration`  
**Status:** Integration handoff for implementation

## Mandatory First Instruction

```text
Read docs/README_FOR_AI_DEVELOPERS.md before doing anything.
```

Then read the frozen Enterprise V1 documents available in this repository, including this handoff.

## Important Documentation Note

The authoritative Enterprise README references several earlier architecture filenames that are not present in the Enterprise Core GitHub repository. Do not invent those missing documents and do not stop solely because those legacy filenames are absent. Use the frozen standards copied into this repository, the tested public Enterprise Core interfaces, and this handoff as the Stage 9 integration basis. Stop only when a genuine implementation question cannot be resolved from the Swing repository or the public Enterprise Core contracts.

## Enterprise Version 1 Work Already Completed

The following work exists in `percyagenticmay27-commits/Trade-Dividend-Bot` and has passed targeted local QA.

### Stage 2 — Enterprise Market Data

Implemented under `enterprise_core/market_data/`:

- canonical market-data requests, bars, and responses;
- provider interface and provider-priority/fallback engine;
- Yahoo read-only provider;
- Robinhood read-only injected-runtime boundary;
- validated historical cache provider;
- normalization, validation, and quality assessment;
- cache-write orchestration;
- provider diagnostics;
- configuration-driven provider construction;
- Dividend Bot compatibility adapter.

Targeted QA result: **28 passed**.

### Stage 3 — Enterprise Strategy Registry

Implemented under `enterprise_core/strategy_registry/`:

- `StrategyManifest`;
- strict manifest loader;
- compatibility and paper-only validator;
- stable-ID registry;
- filesystem discovery;
- contract-based health monitor.

Targeted QA result: **22 passed**.

### Stage 4 — AI CIO Discovery

Implemented under `enterprise_core/ai_cio/`:

- contract-only strategy discovery;
- stable inventory records;
- health inclusion;
- deterministic ordering;
- duplicate and invalid strategy rejection;
- JSON discovery snapshots.

Targeted QA result: **10 passed**.

### Stage 5 — Enterprise Event Bus

Implemented under `enterprise_core/event_bus/`:

- canonical `EnterpriseEvent`;
- exact-type and wildcard subscriptions;
- duplicate subscription protection;
- subscriber failure isolation;
- append-only JSON Lines event storage.

Targeted QA result: **14 passed**.

### Stage 6 — Enterprise Plugin SDK

Implemented under `enterprise_core/plugin_sdk/`:

- `PluginContext`;
- `PluginRunResult`;
- abstract `EnterpriseStrategyPlugin`;
- restricted `ServiceRegistry`;
- safe `PluginRuntime` lifecycle;
- strategy-ID and required-service validation.

Targeted QA result: **15 passed**.

### Stage 7 — Dividend Bot Enterprise Integration

Implemented under `enterprise_core/integrations/`:

- `DividendBotEnterprisePlugin`;
- existing paper-cycle callback delegation;
- Enterprise manifest, status, health, and outputs publication;
- failure and shutdown contract updates;
- no changes to Dividend Bot calculations.

Targeted QA result: **10 passed**.

### Stage 8 — Enterprise Runtime Bootstrap

Implemented under `enterprise_core/runtime/`:

- paper-only `EnterpriseRuntime` composition;
- Plugin SDK lifecycle integration;
- restricted service enforcement;
- lifecycle events;
- runtime snapshots;
- initialization, completion, failure, and shutdown handling.

Targeted QA result: **10 passed**.

## Stage 9 Purpose

Integrate the existing Swing Trader as an Enterprise strategy plugin without rewriting its strategy logic, scoring engines, lifecycle rules, state, schemas, or reports.

## Required Stable Identity

Use:

```text
strategy_id=STRATEGY-SWING-001
```

The display name may remain the existing Swing Trader name, but the stable strategy ID must not change after publication.

## Required Integration Boundary

Create a compatibility adapter named:

```text
SwingTraderEnterprisePlugin
```

It must implement the public `EnterpriseStrategyPlugin` boundary and delegate one cycle to the existing paper-only Swing Trader entrypoint or orchestration function.

The adapter must not reimplement:

- discovery or watchlist logic;
- Opportunity Quality;
- Entry Score;
- market intelligence;
- market regime;
- momentum scoring;
- technical or fundamental analysis;
- Strategy A or Strategy B;
- portfolio allocation or portfolio management;
- reporting calculations;
- existing JSON, CSV, or Markdown generation.

## Required Enterprise Contracts

The integration must publish and maintain:

- `manifest.json`;
- `status.json`;
- `health.json`;
- `outputs.json`.

The manifest must declare:

- stable strategy ID and name;
- semantic version;
- lifecycle status;
- certification level;
- entrypoint;
- capabilities;
- permissions;
- required Enterprise services;
- output paths;
- state ownership;
- `paper_trade_mode=true`;
- `live_trading_enabled=false`;
- `broker_execution_enabled=false`.

## Market Data Integration Rule

The final Enterprise-integrated runtime must obtain market data through the Enterprise Market Data service or its declared compatibility boundary. Do not add new direct Yahoo, Robinhood, Codex, Robinhood MCP, or provider-adapter calls.

Existing direct market-data calls found in legacy Swing modules must be inventoried before modification. Replace them only through targeted compatibility injection, with regression tests proving that calculations and output schemas remain unchanged.

## Runtime Integration

The plugin must:

1. initialize through `PluginContext`;
2. validate required services through `ServiceRegistry`;
3. run one existing paper-only Swing cycle;
4. return a valid `PluginRunResult`;
5. update status, health, and outputs contracts;
6. publish lifecycle events through the Enterprise Event Bus when available;
7. shut down without altering strategy-owned paper state.

## Permanent Safety State

```text
paper_trade_mode=True
live_trading_enabled=False
broker_execution_enabled=False
```

No real orders, broker execution, account management, capital movement, or Robinhood execution may be added.

## Required Tests

Add targeted tests for:

- stable strategy identity;
- plugin initialization;
- delegation to the existing Swing paper cycle;
- successful `PluginRunResult`;
- failure propagation;
- safe shutdown;
- manifest generation and validation;
- status, health, and outputs generation;
- output-path containment;
- required-service enforcement;
- Strategy Registry discovery;
- AI CIO discovery compatibility;
- Enterprise Runtime execution;
- paper-only safety flags;
- no broker execution;
- no changes to existing public Swing schemas.

Run the complete existing Swing Trader test suite after the targeted integration tests. Production strategy code must not be changed merely to make a test fixture pass unless the test exposes a genuine compatibility defect.

## Definition of Done

Stage 9 is complete only when:

- the existing Swing Trader tests pass;
- targeted Enterprise integration tests pass;
- the four Enterprise contracts validate;
- AI CIO discovery can recognize the strategy through contracts alone;
- the Swing Trader can run one paper cycle through the Enterprise Runtime;
- existing calculations and reports remain unchanged;
- no direct provider or broker capability is added;
- the permanent safety state remains enforced.

# Thesis Monitor Version 2.0 Freeze

## Purpose

Thesis Monitor V2 is the current-universe thesis-health authority for the paper-only Swing Bot. It replaces handwritten symbol thesis fixtures with dynamic evidence assembled from the active ranked watchlist and current authoritative Opportunity Quality evidence.

The legacy `thesis_monitor.py` Version 1.4 remains for compatibility/history only. Its `Strategy A` / `Strategy B` report must not govern the modern committee pipeline.

## Dynamic Architecture

V2 is dynamic in the parts that should change automatically:

- Active symbols come from the current ACTIVE ranked watchlist.
- Underlying-to-vehicle and frozen Primary IDs come from `configs/frozen_strategy_assignments.json` when available.
- Evidence values and provenance come from current `opportunity_quality_inputs.json`.
- Current Opportunity Quality comes from `opportunity_quality_report.json`.
- Prior V2 review values are used to measure change from the previous run.
- No handwritten per-symbol thesis text is required.
- New active symbols enter the thesis universe automatically when evidence is available.
- Removed/inactive symbols leave the current review universe automatically.

V2 is intentionally **not dynamically self-tuning**. Component weights and thresholds are frozen for Version 2.0 and may change only through an explicit governed version change.

## Frozen Component Weights

- Fundamental Analysis: 25%
- Market Intelligence: 20%
- Conviction: 20%
- Momentum: 10%
- Technical Analysis: 10%
- Market Regime Support: 10%
- Portfolio Risk Adjustment: 5%

The thesis model intentionally gives the greatest weight to the durability of the company/opportunity and supporting intelligence/conviction rather than entry timing.

## Frozen Thresholds

- Strong: thesis health >= 85
- Intact: thesis health >= 70
- Weakening: thesis health >= 55
- Broken: thesis health < 55
- Minimum current evidence components: 5
- Weak component threshold: < 55
- Three or more weak components force at least Weakening
- A thesis-health decline of 12 or more points from the previous V2 review forces at least Weakening

## Missing Evidence

Missing current evidence is not converted to zero for thesis-health calculation.

If fewer than five thesis components are available:

- `thesis_state = unknown`
- `thesis_intact = null`
- `evidence_status = EVIDENCE_PENDING`

This produces a governed wait state rather than manufacturing a rejection or approval.

## Independence Rules

Thesis Monitor V2 must not use:

- Entry Score
- frozen Primary BUY/SELL signals
- historical strategy backtest performance
- Shadow strategy performance
- synthetic leveraged returns
- broker state
- live trading state
- manually handwritten symbol scores

Entry Score answers whether timing is favorable. Thesis Monitor answers whether the opportunity rationale remains supported. The two remain independent committee requirements.

## Modern Identity

Each review may identify:

- `underlying_symbol`
- `vehicle_symbol`
- `primary_strategy_id`

V2 does not restrict strategies to legacy `Strategy A` / `Strategy B` names.

## Outputs

- `results/thesis_monitor_v2_report.json`
- `results/thesis_monitor_v2_report.md`

The legacy `results/thesis_monitor_report.json` is not overwritten.

## Committee Authority

`opportunity_quality_inputs.py` recognizes `thesis_monitor_v2_report.json` as the current thesis source and intentionally excludes the legacy Version 1.4 thesis artifact from current committee evidence.

A candidate is not made allocation-eligible by Thesis Monitor alone. Opportunity Quality, Entry Score, thesis intact, forward Primary confidence, allocation governance, and all existing paper-only controls remain separate.

## Safety

- `paper_trade_mode=True`
- advisory only
- no broker execution
- no real order placement
- no capital movement
- no Step 7 behavior change in Version 2.0 development

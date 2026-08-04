# Opportunity Quality Runtime Report Generator Version 1

## Purpose

Generate the authoritative runtime Opportunity Quality report set required by the existing Opportunity Quality Publisher and Enterprise KPI Publisher v2.1.

The generator does not change the frozen Opportunity Quality calculation. It assembles existing symbol-level Swing evidence, invokes `OpportunityQualityEngine`, and publishes the standard reports.

## Inputs

By default the generator checks existing files under `results/`:

- `opportunity_quality_inputs.json`
- `portfolio_allocations.json`
- `watchlist_report.json`
- `confidence_report.json`
- `momentum_scores.json`
- `market_intelligence.json`
- `market_regime.json`
- `technical_analysis.json`
- `fundamental_analysis.json`

Additional JSON or CSV inputs may be supplied with repeated `--source` arguments.

Evidence is merged by uppercase symbol. Recognized aliases are mapped into the frozen engine component fields. Missing component evidence remains absent and is scored as zero by the engine's permanent rule.

## Outputs

- `results/opportunity_quality_report.json`
- `results/opportunity_quality_report.csv`
- `results/opportunity_quality_report.md`

All three outputs are written atomically. A failed generation does not publish a partial replacement.

## Permanent architecture rules

- Missing evidence equals zero.
- Entry Score is display-only.
- Entry Score is not included in Opportunity Quality.
- Frozen Version 1.2 component weights are reused from `opportunity_quality_engine.py`.
- No strategy calculation is duplicated or modified.
- Paper-only safety remains locked.
- No broker, order, transfer, or capital-movement operation is available.

## Run

```bash
python run_opportunity_quality_runtime_report.py \
  --results-dir results \
  --system-mode QA
```

With explicit sources:

```bash
python run_opportunity_quality_runtime_report.py \
  --results-dir results \
  --source results/portfolio_allocations.json \
  --source results/watchlist_report.json
```

Then publish the canonical CIO artifact:

```bash
python publish_opportunity_quality.py \
  --source results/opportunity_quality_report.json \
  --output results/opportunity_quality.json
```

Then republish Enterprise KPI v2.1.

## Failure behavior

Generation fails safely when no symbol-level evidence exists, input JSON is malformed, or a score is outside 0 through 100. Existing valid reports are preserved because publication uses atomic replacement only after successful calculation and serialization.

# Opportunity Quality Publisher Version 1.0

## Purpose

Publish a canonical, read-only Opportunity Quality artifact for Enterprise KPI and AI CIO consumption without changing the frozen Opportunity Quality calculations.

## Source

`results/opportunity_quality_report.json`

The source must be produced by `opportunity_quality_engine.py` and preserve these permanent rules:

- Missing evidence equals 0.
- Entry Score is display-only.
- Entry Score is not part of Opportunity Quality.
- QA and LIVE calculations are identical.
- Paper trading only.

## Output

`results/opportunity_quality.json`

The canonical artifact includes:

- top-level `opportunity_quality_score`
- top-level `opportunity_quality_level`
- top opportunity
- average Opportunity Quality score
- opportunity count
- deterministically ranked opportunities
- source component weights
- evidence status
- warnings and errors
- permanent paper-safety flags

The top-level score is the score of the highest-ranked current opportunity. The publisher does not recalculate or alter any component score.

## Safety

The publisher is reporting-only and rejects unsafe source evidence. It never imports the Dividend Bot, contacts a broker, places orders, moves capital, or writes directly to a database.

## Commands

```bash
python -m py_compile src/swing_trade_bot/opportunity_quality_publisher.py
python -m py_compile publish_opportunity_quality.py
python -m pytest tests/test_opportunity_quality_publisher.py -v
```

Generate the source report using the existing engine launcher or module, then publish canonical evidence:

```bash
python publish_opportunity_quality.py \
  --source results/opportunity_quality_report.json \
  --output results/opportunity_quality.json
```

Republish Enterprise KPI v2.1 afterward:

```bash
python publish_enterprise_strategy_kpis_v21.py \
  --strategy-allocations-file results/enterprise_strategy_allocations.json
```

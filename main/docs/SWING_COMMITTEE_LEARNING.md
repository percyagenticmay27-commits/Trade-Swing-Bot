# Swing Committee Learning Foundation

## Purpose

Phase 9E.5 evaluates the effectiveness of each Swing committee without modifying policy automatically.

The design follows the Dividend Bot learning model:

- append-only evidence
- deterministic observation and proposal identifiers
- observation-first learning
- minimum evidence requirements
- advisory proposals
- explicit human approval
- no brokerage execution or capital movement

## Independent Learning Dimensions

The module separates:

### Decision Quality

- policy compliance
- evidence completeness
- committee-jurisdiction compliance
- trace completeness

### Outcome Quality

- return percentage
- maximum favorable excursion
- maximum adverse excursion
- rank-to-outcome alignment
- replacement outperformance

A compliant decision may still have a poor market outcome. A profitable outcome does not prove that a poor decision process was acceptable.

## Minimum Evidence

Learning remains `OBSERVATION_ONLY` until all requirements are met:

```text
30 completed decision traces
6 months of history
10 observations for every committee
```

After the minimums are met, learning becomes `ELIGIBLE_FOR_REVIEW`.

## Committee Coverage

```text
DISCOVERY_COMMITTEE
OPPORTUNITY_COMMITTEE
ENTRY_COMMITTEE
PORTFOLIO_COMMITTEE
EXIT_COMMITTEE
```

The Entry Committee is evaluated using both approved entries and vetoed entries. Outcome measurements should be attached at 3, 5, 10, and 20 trading days when available.

## Proposal Types

```text
EVIDENCE_SOURCE_REVIEW
THRESHOLD_REVIEW
COMMITTEE_PROCESS_REVIEW
STRATEGY_PREFERENCE_REVIEW
NO_CHANGE
```

All proposals:

```text
requires_human_approval=True
automatic_policy_change=False
```

## Safety

Permanent rules:

```text
paper_trade_mode=True
advisory_only=True
append_only=True
automatic_policy_change_allowed=False
human_approval_required=True
broker_execution_allowed=False
capital_movement_allowed=False
```

## Files

```text
configs/swing_committee_learning.json
src/swing_trade_bot/swing_committee_learning.py
tests/test_swing_committee_learning.py
docs/SWING_COMMITTEE_LEARNING.md
```

## Validation

From the `main` directory:

```cmd
python -m py_compile src\swing_trade_bot\swing_committee_learning.py
python -m pytest tests\test_swing_committee_learning.py -v
```

Then run the complete committee group:

```cmd
python -m pytest tests\test_swing_committee_governance.py tests\test_swing_strategy_capability_profiles.py tests\test_swing_committee_traceability.py tests\test_swing_committee_learning.py -v
```

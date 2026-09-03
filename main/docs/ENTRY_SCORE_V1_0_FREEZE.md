# Entry Score Version 1.0 Freeze

## Purpose

Entry Score is the Swing Bot Entry Committee timing score. It answers whether the current completed-daily-bar environment supports entry consideration.

Entry Score is independent from Opportunity Quality and independent from the assigned frozen strategy's exact BUY trigger.

## Permanent Entry Committee Gate

A candidate may reach the Portfolio Committee only when all of the following are true:

- Opportunity Quality Score >= 70
- Entry Score >= 70
- thesis_intact = true

Entry Score does not alter Opportunity Quality.

## Price Evidence Authority

For mapped leveraged Swing vehicles, Entry Score is calculated from the unleveraged signal/underlying symbol.

Examples:

- NVDA -> NVDX uses NVDA Entry Score evidence
- QQQ -> TQQQ uses QQQ Entry Score evidence
- NFLX -> NFLU uses NFLX Entry Score evidence

The leveraged vehicle remains the authority for actual paper fills, market value, P/L, profit protection, and catastrophic vehicle risk.

No synthetic leveraged return may be used to manufacture Entry Score evidence.

## Completed-Bar Rule

Entry Score uses completed daily bars only.

Partial intraday daily bars are not authoritative Entry Score evidence.

## Version 1.0 Components

The Version 1.0 score is a transparent 100-point model:

- Daily RSI Direction: 20 points
- Daily Stochastic RSI K/D Relationship: 20 points
- Momentum Direction: 20 points
- Volume Confirmation: 15 points
- Price Trend Confirmation: 15 points
- Extension and Pullback Risk: 10 points

Total maximum: 100 points.

Minimum passing Entry Score: 70.

## Daily RSI Direction

Indicator: Wilder RSI(14).

Direction compares the latest completed daily RSI with the previous completed daily RSI.

A change within +/-0.25 RSI points is treated as flat.

Scoring:

- Rising and RSI >= 50: 20
- Rising and RSI 40 through 49.99: 15
- Rising and RSI < 40: 10
- Flat: 5
- Falling and RSI >= 50: 5
- Falling and RSI < 50: 0

## Daily Stochastic RSI K/D Relationship

Parameters:

- RSI length: 14
- Stochastic lookback: 14
- K smoothing: 3
- D smoothing: 3

Scoring:

- Fresh bullish K crossover above D: 20
- K > D and both rising: 20
- K > D and K approximately flat: 15
- K > D but K declining: 10
- K approximately equals D: 5
- K < D: 0

K and D are approximately equal when their absolute difference is <= 1.0.
K is approximately flat when it is no more than 1.0 point below its prior value.

Overbought Stochastic RSI is not separately penalized here. Extension risk is evaluated independently to avoid double punishment.

## Momentum Direction

Indicator: MACD(12,26,9).

Scoring:

- Fresh bullish MACD crossover: 20
- MACD > signal and histogram increasing: 20
- MACD > signal but histogram weakening: 15
- MACD < signal but histogram improving: 10
- MACD approximately neutral: 5
- MACD < signal and deteriorating: 0

Approximate neutrality uses a histogram tolerance equal to 0.1% of the current close.

## Volume Confirmation

Indicator:

Current completed daily volume divided by the prior 20 completed daily bars' average volume.

Scoring before directional cap:

- Ratio >= 1.50: 15
- Ratio >= 1.20: 12
- Ratio >= 1.00: 10
- Ratio >= 0.80: 5
- Ratio < 0.80: 0

If the current close is below the previous completed daily close, Volume Confirmation is capped at 5 points. High volume on a negative bar does not receive full bullish confirmation.

## Price Trend Confirmation

Indicators:

- Daily EMA20
- Daily EMA50
- Daily Close

Scoring:

- Close > EMA20 > EMA50: 15
- Close > EMA20 while EMA20 <= EMA50: 10
- Close below EMA20 but above EMA50: 5
- Close below both EMA20 and EMA50: 0

This component is strategy-independent and must not reproduce Strategy F, Zero Lag, Keltner, or any other frozen strategy's exact entry logic.

## Extension and Pullback Risk

Extension is measured as:

`(Close - EMA20) / EMA20 * 100`

Scoring:

- 0% through +3% above EMA20: 10
- >+3% through +5%: 8
- >+5% through +8%: 5
- >+8% through +10%: 2
- >+10%: 0
- 0% through -3% below EMA20: 7
- below -3% through -5%: 4
- more than 5% below EMA20: 0

## Missing Evidence

If any required component cannot be calculated from authoritative completed daily evidence:

- entry_score = null
- entry_status = EVIDENCE_PENDING
- entry_score_gate_passed = false

Missing evidence must not be treated as bearish evidence and must not be converted into a partial numeric score.

## Output Contract

Authoritative outputs:

- `results/entry_score_report.json`
- `results/entry_score_report.csv`

The JSON report exposes each component's points, maximum points, status, and calculation evidence so the final Entry Score is reproducible.

`opportunity_quality_inputs.py` already recognizes `results/entry_score_report.json` as an Entry Score source.

## Architecture Rules

- Paper-only
- Advisory-only
- No broker execution
- No real order placement
- No capital movement
- Entry Score is independent from Opportunity Quality
- Frozen strategy BUY signals are not part of Entry Score
- Market Regime is not a hard Entry veto
- Signal/underlying symbol is Entry Score price authority
- Leveraged vehicle is not used to synthesize Entry Score
- Missing required evidence fails closed as EVIDENCE_PENDING
- Entry Score threshold remains 70
- Thesis integrity remains an independent requirement

## Frozen Module

- `src/swing_trade_bot/entry_score_engine.py`

## Validation

Run:

```bash
python -m py_compile src/swing_trade_bot/entry_score_engine.py
pytest tests/test_entry_score_engine.py -v
```

After tests pass, generate the current evidence artifact with:

```bash
python -m swing_trade_bot.entry_score_engine \
  --results-dir results \
  --data-dir data
```

Do not wire Entry Score into paper allocation or execution by bypassing the existing Opportunity, Entry, Portfolio, or frozen-strategy governance layers.

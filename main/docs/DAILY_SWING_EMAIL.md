# Daily Swing CSV Email

## Purpose

Send the paper-only Trade Swing Bot's daily CSV evidence through the existing shared SendGrid account on DigitalOcean.

## Shared configuration

The sender reads:

`/home/tradebot/.config/tradebot/email.env`

Required settings:

- `SENDGRID_API_KEY`
- `SENDGRID_FROM_EMAIL`
- `SENDGRID_FROM_NAME`
- `SENDGRID_REPLY_TO`
- `REPORT_RECIPIENT`

The API key must retain its `SG.` prefix. The environment file must not be committed.

## Outputs

- `results/daily_swing_summary.csv`
- `results/swing_email_delivery_log.csv`
- `results/swing_email_delivery_status.json`

## Attachments

Required:

- `results/daily_swing_summary.csv`
- `results/paper_ledger/paper_performance.csv`

Optional:

- `results/opportunity_quality_report.csv`
- `results/watchlist_report.csv`
- `results/paper_ledger/paper_portfolio_positions.csv`
- `results/paper_ledger/managed_trade_history.csv`

Missing optional files create warnings. Missing required files prevent sending.

## Safety

The sender is reporting-only and permanently locks paper-trading safety values. It has no brokerage, order, cancellation, transfer, or capital-movement operations and does not import Trade-Dividend-Bot production modules.

## Manual test

From `/home/tradebot/Trade-Swing-Bot/main`:

```bash
source .venv/bin/activate
python -m py_compile src/swing_trade_bot/daily_swing_email.py
python -m py_compile send_daily_swing_email.py
python -m pytest tests/test_daily_swing_email.py -v
python send_daily_swing_email.py
```

Do not install the scheduled timer until the controlled manual email is received and the delivery status is `SENT`.

## Intended schedule

After manual validation, schedule the service for 3:30 PM Central, Monday through Friday. Use a systemd timer with the `America/Chicago` timezone so daylight-saving changes are handled correctly.

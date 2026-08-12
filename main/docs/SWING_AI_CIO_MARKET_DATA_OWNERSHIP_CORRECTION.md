# Swing / AI CIO Market Data Ownership Correction

Date: 2026-08-12
Status: ACTIVE

## Why this correction exists

DigitalOcean validation of the current AI CIO architecture found that the previously expected host artifacts:

- `/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_contract.json`
- `/home/tradebot/Trade-Dividend-Bot/results/enterprise_market_data_status.json`

are not published by the current AI CIO host. The only matching host-side file found during the controlled diagnostic was `market_data_snapshot.json`.

The current authoritative Swing-to-AI-CIO handoff states that Swing owns its market data and that the sole cross-repository interface is AI CIO reading Swing registration/results. Therefore the earlier Phase 2 launcher dependency on Dividend-hosted Enterprise market-data contract/status artifacts is no longer appropriate for the current architecture.

## Permanent decision

`run_swing_bot_cycle.py` must refresh Swing-owned market data before the paper strategy cycle. It must not require Dividend-hosted market-data contract/status files to start a Swing cycle.

Swing market data refresh uses the existing repository-owned provider-neutral acquisition layer in `src/swing_trade_bot/data_download.py`, which already supports Yahoo download, Yahoo chart fallback, Stooq fallback, validation, and local Swing `data/` storage.

The cycle must still fail closed when required Swing market data cannot be refreshed or validated.

## Implemented correction

- Added `src/swing_trade_bot/swing_market_data_refresh.py`.
- Updated `run_swing_bot_cycle.py` to call `refresh_swing_market_data()` instead of `sync_enterprise_market_data.main()`.
- The new refresh publishes `results/market_data_refresh_status.json` atomically inside the Swing repository.
- Status carries `SWING-001` ownership and explicit paper/advisory safety locks.
- No Dividend production imports are used.
- No Dividend results/config files are written.
- Existing `sync_enterprise_market_data.py` is retained for backward compatibility/history but is no longer the authoritative daily-cycle gate.
- Updated launcher regression tests.
- Added dedicated Swing-owned market-refresh regression tests.

## Required server validation

After pulling the correction on DigitalOcean:

1. compile `run_swing_bot_cycle.py` and `src/swing_trade_bot/swing_market_data_refresh.py`;
2. run `tests/test_swing_market_data_refresh.py`;
3. rerun `tests/test_run_swing_bot_cycle.py`;
4. run the controlled `python run_swing_bot_cycle.py`;
5. inspect `results/market_data_refresh_status.json` before refreshing AI CIO.

## Safety rule

Do not bypass failed market-data validation and do not fabricate a Dividend-hosted contract file merely to satisfy the old Phase 2 integration path.

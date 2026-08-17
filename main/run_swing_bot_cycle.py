"""Authoritative server launcher for the paper-only Swing Bot cycle.

Swing refreshes Enterprise discovery intake and its own authoritative market
inputs before strategy-report publication. A successful strategy-report cycle is
then followed by Enterprise KPI publication. Any required evidence failure blocks
the cycle safely.
"""
from __future__ import annotations

from publish_enterprise_strategy_kpis_v21 import publish
from swing_trade_bot.enterprise_discovery_bucket import refresh_enterprise_discovery_inputs
from swing_trade_bot.swing_daily_cycle import main as run_cycle
from swing_trade_bot.swing_market_data_refresh import refresh_swing_market_data


def main() -> int:
    refresh_enterprise_discovery_inputs()

    market_data_status = refresh_swing_market_data()
    if market_data_status != 0:
        return market_data_status

    status = run_cycle()
    if status != 0:
        return status

    publish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

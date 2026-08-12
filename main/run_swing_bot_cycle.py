"""Authoritative server launcher for the paper-only Swing Bot cycle.

Fresh normalized Enterprise market data is synchronized before strategy-report
publication. A successful strategy-report cycle is then followed by Enterprise
KPI publication. Any required market-data failure blocks the cycle safely.
"""
from __future__ import annotations

from publish_enterprise_strategy_kpis_v21 import publish
from swing_trade_bot.swing_daily_cycle import main as run_cycle
from sync_enterprise_market_data import main as sync_market_data


def main() -> int:
    market_data_status = sync_market_data()
    if market_data_status != 0:
        return market_data_status

    status = run_cycle()
    if status != 0:
        return status

    publish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

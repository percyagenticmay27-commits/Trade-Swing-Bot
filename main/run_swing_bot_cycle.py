"""Authoritative server launcher for the paper-only Swing Bot cycle.

A successful strategy-report cycle is followed by Enterprise KPI publication.
The Swing email continues to validate and require that artifact independently.
"""
from __future__ import annotations

from publish_enterprise_strategy_kpis_v21 import publish
from swing_trade_bot.swing_daily_cycle import main as run_cycle


def main() -> int:
    status = run_cycle()
    if status != 0:
        return status
    publish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Authoritative server launcher for the paper-only Swing Bot cycle.

Swing refreshes Enterprise discovery intake and its own authoritative market
inputs before strategy-report publication. Optional user vetoes are blocking
exceptions only; absence of a veto preserves normal autonomous paper evaluation.
A successful strategy-report cycle is persisted into Swing-owned discovery state
before Enterprise KPI publication.
"""
from __future__ import annotations

from publish_enterprise_strategy_kpis_v21 import publish
from swing_trade_bot.enterprise_candidate_state_sync import sync_candidate_state_from_watchlist
from swing_trade_bot.enterprise_discovery_bucket import refresh_enterprise_discovery_inputs
from swing_trade_bot.enterprise_financial_health import refresh_enterprise_financial_health_inputs
from swing_trade_bot.swing_daily_cycle import main as run_cycle
from swing_trade_bot.swing_market_data_refresh import refresh_swing_market_data
from swing_trade_bot.user_veto_control import apply_active_vetoes_to_runtime_candidates


def main() -> int:
    refresh_enterprise_discovery_inputs()
    apply_active_vetoes_to_runtime_candidates()
    refresh_enterprise_financial_health_inputs()

    market_data_status = refresh_swing_market_data()
    if market_data_status != 0:
        return market_data_status

    status = run_cycle()
    if status != 0:
        return status

    sync_candidate_state_from_watchlist()
    publish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

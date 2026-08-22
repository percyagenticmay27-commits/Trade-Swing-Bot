"""Authoritative server launcher for the paper-only Swing Bot cycle.

Swing refreshes Enterprise discovery intake and its own authoritative market
inputs before strategy-report publication. AI CIO discovery is nomination-only and
never supplies Swing strategy scores. Optional Discovery Leadership is preserved
as read-only upstream context and cannot directly change Opportunity Quality,
Entry Score, lifecycle state, or execution. Optional user vetoes are blocking
exceptions only; absence of a veto preserves normal autonomous paper evaluation.
A successful strategy-report cycle is persisted into Swing-owned discovery state
before Enterprise KPI publication.

Manual SHADOW strategies run after the normal Swing cycle and candidate-state
sync. Shadow research is evidence-only and non-blocking: it cannot reserve or
move capital, create paper positions, place orders, or promote a strategy.
"""
from __future__ import annotations

from publish_enterprise_strategy_kpis_v21 import publish
from swing_trade_bot.enterprise_candidate_state_sync import sync_candidate_state_from_watchlist
from swing_trade_bot.enterprise_discovery_bucket import refresh_enterprise_discovery_inputs
from swing_trade_bot.enterprise_discovery_leadership_context import (
    refresh_enterprise_discovery_leadership_context,
)
from swing_trade_bot.manual_strategy_shadow_workflow import build_and_write_shadow_strategies
from swing_trade_bot.swing_daily_cycle import main as run_cycle
from swing_trade_bot.swing_market_data_refresh import refresh_swing_market_data
from swing_trade_bot.user_veto_control import apply_active_vetoes_to_runtime_candidates


def _run_shadow_research_nonblocking() -> None:
    """Refresh research evidence without gaining authority over the paper cycle."""
    try:
        result = build_and_write_shadow_strategies()
    except Exception as exc:  # fail visible, but research cannot block normal paper operation
        print(f"WARNING: shadow strategy research refresh failed: {type(exc).__name__}: {exc}")
        return
    available = sum(
        1 for row in result.get("rows", [])
        if row.get("evidence_status") == "AVAILABLE"
    )
    print(
        "Shadow strategy research refresh: "
        f"{len(result.get('rows', []))} assignment(s); {available} with evidence"
    )


def main() -> int:
    refresh_enterprise_discovery_inputs()
    refresh_enterprise_discovery_leadership_context()
    apply_active_vetoes_to_runtime_candidates()

    market_data_status = refresh_swing_market_data()
    if market_data_status != 0:
        return market_data_status

    status = run_cycle()
    if status != 0:
        return status

    sync_candidate_state_from_watchlist()
    _run_shadow_research_nonblocking()
    publish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

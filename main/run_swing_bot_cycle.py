"""Authoritative server launcher for the paper-only Swing Bot cycle.

Swing refreshes Enterprise discovery intake and its own authoritative market
inputs before strategy-report publication. AI CIO discovery is nomination-only and
never supplies Swing strategy scores. Optional Discovery Leadership is preserved
as read-only upstream context and cannot directly change Opportunity Quality,
Entry Score, lifecycle state, or execution. Optional user vetoes are blocking
exceptions only; absence of a veto preserves normal autonomous paper evaluation.
A successful strategy-report cycle is persisted into Swing-owned discovery state
before Enterprise KPI publication.

Manual SHADOW strategies and frozen-engine Primary/Shadow stacks run after the
normal Swing cycle and candidate-state sync. Both research paths are evidence-only
and non-blocking: neither can reserve/move capital, create paper positions, or
place orders. Monthly promotion review and veto resolution remain separate
governance steps.
"""
from __future__ import annotations

from publish_enterprise_strategy_kpis_v21 import publish
from swing_trade_bot.enterprise_candidate_state_sync import sync_candidate_state_from_watchlist
from swing_trade_bot.enterprise_discovery_bucket import refresh_enterprise_discovery_inputs
from swing_trade_bot.enterprise_discovery_leadership_context import (
    refresh_enterprise_discovery_leadership_context,
)
from swing_trade_bot.frozen_strategy_operational_workflow import build_and_write_frozen_strategy_evidence
from swing_trade_bot.manual_entry_strategy_form_contract import (
    DEFAULT_OUTPUT_PATH as DEFAULT_FORM_CONTRACT_PATH,
    DEFAULT_REGISTRY_PATH as DEFAULT_MANUAL_STRATEGY_REGISTRY_PATH,
)
from swing_trade_bot.manual_strategy_shadow_workflow import build_and_write_shadow_strategies
from swing_trade_bot.shadow_promotion_lifecycle import process_pending_promotions
from swing_trade_bot.shadow_promotion_review_workflow import build_monthly_promotion_review
from swing_trade_bot.strategy_assignment_shadow_report import DEFAULT_OUTPUT_PATH as DEFAULT_ASSIGNMENT_REPORT_PATH
from swing_trade_bot.swing_daily_cycle import main as run_cycle
from swing_trade_bot.swing_market_data_refresh import refresh_swing_market_data
from swing_trade_bot.user_veto_control import apply_active_vetoes_to_runtime_candidates


def _run_shadow_research_nonblocking() -> None:
    """Refresh legacy declarative Shadow evidence without gaining paper authority."""
    try:
        result = build_and_write_shadow_strategies()
    except Exception as exc:
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


def _run_frozen_strategy_research_nonblocking() -> None:
    """Refresh frozen-engine Primary/Shadow evidence using current Primary shares."""
    try:
        result = build_and_write_frozen_strategy_evidence()
    except Exception as exc:
        print(f"WARNING: frozen strategy research refresh failed: {type(exc).__name__}: {exc}")
        return
    rows = result.get("rows", [])
    available = sum(1 for row in rows if row.get("evidence_status") == "AVAILABLE")
    missing = sum(1 for row in rows if row.get("evidence_status") == "MISSING_INTRADAY_MARKET_DATA")
    print(
        "Frozen strategy research refresh: "
        f"{len(rows)} assignment(s); {available} with evidence; {missing} missing intraday data"
    )


def _run_shadow_promotion_review_nonblocking() -> None:
    """Run at most one comparable legacy Primary-versus-Shadow review per month."""
    try:
        report = build_monthly_promotion_review()
    except Exception as exc:
        print(f"WARNING: shadow promotion review failed: {type(exc).__name__}: {exc}")
        return
    reviewed = sum(
        1 for row in report.rows
        if row.status in {"REVIEWED_NOT_QUALIFIED", "QUALIFIED_PENDING_VETO"}
    )
    queued = sum(1 for row in report.rows if row.queued_pending_veto)
    if report.rows:
        print(
            "Shadow promotion review: "
            f"{reviewed} reviewed this month; {queued} queued pending veto"
        )
    for warning in report.warnings:
        print(f"WARNING: {warning}")


def _process_shadow_promotions_nonblocking() -> None:
    """Resolve only already-qualified, expired pending-veto legacy promotion events."""
    try:
        resolved = process_pending_promotions(
            registry_path=DEFAULT_MANUAL_STRATEGY_REGISTRY_PATH,
            form_contract_path=DEFAULT_FORM_CONTRACT_PATH,
            assignment_report_path=DEFAULT_ASSIGNMENT_REPORT_PATH,
        )
    except Exception as exc:
        print(f"WARNING: shadow promotion lifecycle refresh failed: {type(exc).__name__}: {exc}")
        return
    promoted = sum(1 for event in resolved if event.status == "PROMOTED")
    vetoed = sum(1 for event in resolved if event.status == "VETOED")
    if resolved:
        print(
            "Shadow promotion lifecycle: "
            f"{len(resolved)} resolved; {promoted} promoted; {vetoed} vetoed"
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
    _run_frozen_strategy_research_nonblocking()
    _run_shadow_promotion_review_nonblocking()
    _process_shadow_promotions_nonblocking()
    publish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

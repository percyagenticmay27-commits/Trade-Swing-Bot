"""Authoritative server launcher for the paper-only Swing Bot cycle.

Swing refreshes Enterprise discovery intake and its own authoritative market
inputs before strategy-report publication. AI CIO discovery is nomination-only and
never supplies Swing strategy scores. Optional Discovery Leadership is preserved
as read-only upstream context and cannot directly change Opportunity Quality,
Entry Score, lifecycle state, or execution. Optional user vetoes are blocking
exceptions only; absence of a veto preserves normal autonomous paper evaluation.
A successful strategy-report cycle is persisted into Swing-owned discovery state
before Enterprise KPI publication.

Manual SHADOW strategies run as research-only evidence after the normal Swing
cycle. Frozen-engine Primary/Shadow stacks run through one governed paper-only
operational sequence: intraday refresh, DIRECT authority adoption, persistent
Primary quantity snapshot, DIRECT Primary signal execution, paper evidence
reconciliation, reference refresh, then exact-share Primary/Shadow research.
SHADOW assignments never gain paper execution authority. Frozen monthly promotion
review and the three-day user-veto lifecycle remain separate downstream stages.
"""
from __future__ import annotations

from publish_enterprise_strategy_kpis_v21 import publish
from swing_trade_bot.enterprise_candidate_state_sync import sync_candidate_state_from_watchlist
from swing_trade_bot.enterprise_discovery_bucket import refresh_enterprise_discovery_inputs
from swing_trade_bot.enterprise_discovery_leadership_context import (
    refresh_enterprise_discovery_leadership_context,
)
from swing_trade_bot.frozen_primary_operational_cycle import run_frozen_primary_operational_cycle
from swing_trade_bot.frozen_strategy_promotion_workflow import (
    build_frozen_monthly_promotion_review,
    process_frozen_pending_promotions,
)
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


def _run_frozen_primary_operational_cycle_nonblocking() -> None:
    """Run the governed frozen DIRECT/SHADOW paper sequence without blocking CIO publication."""
    try:
        result = run_frozen_primary_operational_cycle()
    except Exception as exc:
        print(f"WARNING: frozen Primary operational cycle failed: {type(exc).__name__}: {exc}")
        return

    intraday_rows = result.get("intraday", {}).get("symbols", [])
    available_data = sum(1 for row in intraday_rows if row.get("status") == "AVAILABLE")
    evidence_rows = result.get("evidence", {}).get("rows", [])
    available_evidence = sum(1 for row in evidence_rows if row.get("evidence_status") == "AVAILABLE")
    executed = int(result.get("executed_event_count", 0))
    print(
        "Frozen Primary operational cycle: "
        f"{available_data}/{len(intraday_rows)} symbol data available; "
        f"{available_evidence}/{len(evidence_rows)} strategy evidence available; "
        f"{executed} paper event(s) executed"
    )

    for row in intraday_rows:
        if row.get("warning"):
            print(f"WARNING: {row.get('symbol')}: {row.get('warning')}")
        if row.get("error"):
            print(f"WARNING: {row.get('symbol')}: {row.get('error')}")
    for row in result.get("execution", {}).get("rows", []):
        if row.get("error"):
            print(f"WARNING: {row.get('symbol')}: {row.get('error')}")


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


def _run_frozen_promotion_review_nonblocking() -> None:
    """Run the frozen-engine five-gate monthly review on exact-share evidence."""
    try:
        report = build_frozen_monthly_promotion_review()
    except Exception as exc:
        print(f"WARNING: frozen promotion review failed: {type(exc).__name__}: {exc}")
        return
    rows = report.get("rows", [])
    reviewed = sum(1 for row in rows if row.get("status") in {"REVIEWED_NOT_QUALIFIED", "QUALIFIED_PENDING_VETO"})
    queued = sum(1 for row in rows if row.get("queued_pending_veto") is True)
    if rows:
        print(
            "Frozen strategy promotion review: "
            f"{reviewed} reviewed this month; {queued} queued pending veto"
        )
    for warning in report.get("warnings", []):
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


def _process_frozen_promotions_nonblocking() -> None:
    """Resolve expired frozen-engine pending-veto events without capital changes."""
    try:
        resolved = process_frozen_pending_promotions()
    except Exception as exc:
        print(f"WARNING: frozen promotion lifecycle refresh failed: {type(exc).__name__}: {exc}")
        return
    promoted = sum(1 for event in resolved if event.status == "PROMOTED")
    vetoed = sum(1 for event in resolved if event.status == "VETOED")
    if resolved:
        print(
            "Frozen strategy promotion lifecycle: "
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
    _run_frozen_primary_operational_cycle_nonblocking()
    _run_shadow_promotion_review_nonblocking()
    _run_frozen_promotion_review_nonblocking()
    _process_shadow_promotions_nonblocking()
    _process_frozen_promotions_nonblocking()
    publish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

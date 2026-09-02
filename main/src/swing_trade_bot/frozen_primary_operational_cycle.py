"""Governed paper-only operational sequence for frozen Primary/Shadow stacks.

The sequence refreshes intraday data, adopts current DIRECT authority, snapshots
Primary shares, processes only DIRECT Primary signals into the paper ledger,
rebuilds authoritative paper evidence, refreshes the persistent reference
quantity, and finally runs Primary/Shadow research evidence using that reference.

SHADOW assignments never reach the execution boundary. No broker or real-capital
surface is enabled by this orchestrator.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .frozen_primary_authority_sync import synchronize_frozen_primary_authority
from .frozen_primary_post_execution_refresh import refresh_frozen_primary_post_execution_evidence
from .frozen_primary_reference_quantity import (
    DEFAULT_REFERENCE_PATH,
    refresh_frozen_primary_reference_quantities,
)
from .frozen_primary_signal_execution_workflow import run_frozen_primary_signal_execution
from .frozen_strategy_operational_workflow import build_and_write_frozen_strategy_evidence
from .intraday_market_data_refresh import refresh_intraday_market_data

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
SHADOW_EXECUTION_ENABLED = False


def run_frozen_primary_operational_cycle(*, repository_root: Path = Path(".")) -> dict[str, Any]:
    """Run the full frozen paper lifecycle in dependency order."""
    root = Path(repository_root).resolve()

    intraday = refresh_intraday_market_data()
    authority = synchronize_frozen_primary_authority()

    reference_before = refresh_frozen_primary_reference_quantities()
    execution = run_frozen_primary_signal_execution()

    post_execution = refresh_frozen_primary_post_execution_evidence(
        repository_root=root,
    )
    reference_after = refresh_frozen_primary_reference_quantities()

    evidence = build_and_write_frozen_strategy_evidence(
        primary_positions_path=DEFAULT_REFERENCE_PATH,
    )

    executed_count = sum(
        len(row.get("executed_events", []))
        for row in execution.get("rows", [])
        if isinstance(row, dict)
    )
    return {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "shadow_execution_enabled": False,
        "sequence": [
            "INTRADAY_REFRESH",
            "DIRECT_AUTHORITY_SYNC",
            "REFERENCE_QUANTITY_BEFORE_EXECUTION",
            "DIRECT_PRIMARY_SIGNAL_EXECUTION",
            "POST_EXECUTION_PAPER_EVIDENCE",
            "REFERENCE_QUANTITY_AFTER_EXECUTION",
            "PRIMARY_SHADOW_RESEARCH_EVIDENCE",
        ],
        "executed_event_count": executed_count,
        "intraday": intraday,
        "authority": authority,
        "reference_before": reference_before,
        "execution": execution,
        "post_execution": post_execution,
        "reference_after": reference_after,
        "evidence": evidence,
    }

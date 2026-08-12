"""Swing-owned market data refresh for the paper-only daily cycle.

The current Enterprise AI CIO contract makes Swing responsible for its own
market inputs. This module refreshes the existing Swing OHLCV data directory
using the repository's established provider-neutral downloader and publishes a
Swing-owned status artifact. It never imports Dividend production code and
never writes to the AI CIO repository.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .data_download import DownloadRun, build_historical_data
from .swing_local_filesystem_integration import atomic_write_json

STRATEGY_ID = "SWING-001"
MODULE_VERSION = "1.0.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_market_data_refresh_status(
    run: DownloadRun,
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build canonical Swing-owned market-data status evidence."""
    summaries = [asdict(summary) for summary in run.summaries]
    for row in summaries:
        for field in ("start_date", "end_date"):
            value = row.get(field)
            row[field] = value.isoformat() if value is not None else None

    failed_symbols = [
        summary.symbol
        for summary in run.summaries
        if summary.error is not None
    ]
    status = "AVAILABLE" if run.validation_ok and not failed_symbols else "BLOCKED"
    return {
        "schema_version": "1.0",
        "module_version": MODULE_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "status": status,
        "market_data_dependent_publication_allowed": status == "AVAILABLE",
        "data_owner": "SWING-001",
        "data_root": "data",
        "validation_ok": run.validation_ok,
        "failed_symbols": failed_symbols,
        "symbols": summaries,
        "validation_summary": run.validation_summary,
        "paper_trade_mode": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "direct_ai_cio_database_writes": False,
    }


def refresh_swing_market_data(
    repository_root: str | Path = ".",
    *,
    years: int = 5,
) -> int:
    """Refresh Swing-owned OHLCV evidence and publish canonical status.

    Returns 0 only when every required symbol refreshes successfully and the
    existing data validator accepts the resulting directory.
    """
    root = Path(repository_root).resolve()
    run = build_historical_data(root / "data", years=years, refresh=False)
    payload = build_market_data_refresh_status(run)
    atomic_write_json(payload, root / "results" / "market_data_refresh_status.json")
    return 0 if payload["market_data_dependent_publication_allowed"] else 2

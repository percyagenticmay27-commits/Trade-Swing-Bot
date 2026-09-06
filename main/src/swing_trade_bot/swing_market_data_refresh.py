"""Swing-owned market data refresh for the paper-only daily cycle."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import StrategyConfig
from .data_download import DownloadRun, build_historical_data
from .data_tools import format_validation_summary, validate_data_directory
from .market_symbol_mapping import get_market_symbol_mapping, required_signal_symbols
from .swing_local_filesystem_integration import atomic_write_json

STRATEGY_ID = "SWING-001"
MODULE_VERSION = "1.1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_market_data_refresh_status(
    run: DownloadRun,
    *,
    generated_at_utc: str | None = None,
    trade_symbols: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Build canonical Swing-owned market-data status evidence."""
    summaries = [asdict(summary) for summary in run.summaries]
    for row in summaries:
        for field in ("start_date", "end_date"):
            value = row.get(field)
            row[field] = value.isoformat() if value is not None else None

    failed_symbols = [summary.symbol for summary in run.summaries if summary.error is not None]
    stale_symbols = [summary.symbol for summary in run.summaries if summary.is_stale]
    status = "AVAILABLE" if run.validation_ok and not failed_symbols else "BLOCKED"
    configured_trade_symbols = trade_symbols or StrategyConfig().symbols
    mappings = []
    for symbol in configured_trade_symbols:
        mapping = get_market_symbol_mapping(symbol)
        mappings.append(
            {
                "trade_symbol": mapping.trade_symbol,
                "valuation_symbol": mapping.valuation_symbol,
                "signal_symbol": mapping.signal_symbol,
                "earnings_symbol": mapping.earnings_symbol,
                "signal_mapping_status": "CONFIGURED" if mapping.signal_symbol else "ETF_NATIVE_REQUIRED",
            }
        )

    warnings = []
    if stale_symbols:
        warnings.append("Stale local history was used only as fallback evidence and publication remains blocked.")
    if failed_symbols:
        warnings.append("One or more required technical-signal symbols could not be refreshed from a live provider.")

    return {
        "schema_version": "1.1",
        "module_version": MODULE_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "status": status,
        "market_data_dependent_publication_allowed": status == "AVAILABLE",
        "data_owner": "SWING-001",
        "data_root": "data",
        "validation_ok": run.validation_ok,
        "failed_symbols": failed_symbols,
        "stale_symbols": stale_symbols,
        "symbols": summaries,
        "symbol_mappings": mappings,
        "validation_summary": run.validation_summary,
        "warnings": warnings,
        "paper_trade_mode": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "direct_ai_cio_database_writes": False,
        "robinhood_market_data_enabled": False,
    }


def refresh_swing_market_data(
    repository_root: str | Path = ".",
    *,
    years: int = 5,
) -> int:
    """Refresh required Swing technical evidence and publish canonical status.

    Single-stock leveraged ETFs with verified mappings use their underlying only
    for technical-signal history. The traded ETF remains the valuation/security
    identity elsewhere. No Robinhood account/auth/order access is introduced.
    """
    root = Path(repository_root).resolve()
    trade_symbols = StrategyConfig().symbols
    signal_symbols = required_signal_symbols(trade_symbols)
    raw_run = build_historical_data(
        root / "data",
        years=years,
        refresh=False,
        symbols=signal_symbols,
    )
    validations = validate_data_directory(root / "data", symbols=signal_symbols)
    run = DownloadRun(
        summaries=raw_run.summaries,
        validation_summary=format_validation_summary(validations),
        validation_ok=all(result.is_valid for result in validations),
    )
    payload = build_market_data_refresh_status(run, trade_symbols=trade_symbols)
    atomic_write_json(payload, root / "results" / "market_data_refresh_status.json")
    return 0 if payload["market_data_dependent_publication_allowed"] else 2

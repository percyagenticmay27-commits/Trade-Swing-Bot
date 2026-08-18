"""Refresh read-only daily OHLCV evidence for the persistent mapped universe."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .data_download import build_historical_data
from .leveraged_vehicle_registry import preferred_vehicle_mapping


def refresh_mapped_underlying_market_data(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    data_dir: str | Path = "data",
    years: int = 5,
    refresh: bool = True,
) -> dict[str, Any]:
    """Refresh mapped underlying OHLCV using the existing read-only provider chain."""
    mapping = preferred_vehicle_mapping(registry_path)
    symbols = tuple(sorted(mapping))
    run = build_historical_data(
        Path(data_dir),
        years=years,
        refresh=refresh,
        symbols=symbols,
    )
    rows = []
    successful = 0
    for summary in run.summaries:
        usable = bool(summary.rows) and summary.error is None and not summary.is_stale
        if usable:
            successful += 1
        rows.append(
            {
                "underlying_symbol": summary.symbol,
                "rows": summary.rows,
                "start_date": summary.start_date.isoformat() if summary.start_date else None,
                "end_date": summary.end_date.isoformat() if summary.end_date else None,
                "source": summary.source,
                "data_source": summary.data_source,
                "is_stale": summary.is_stale,
                "error": summary.error,
                "usable_for_current_quantitative_evidence": usable,
            }
        )
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "provider_policy": "EXISTING_READ_ONLY_MARKET_DATA_CHAIN",
        "mapped_underlying_count": len(symbols),
        "current_market_data_count": successful,
        "validation_ok": run.validation_ok,
        "rows": rows,
    }


if __name__ == "__main__":
    report = refresh_mapped_underlying_market_data()
    print(
        "Mapped underlying market data refresh: "
        f"{report['current_market_data_count']}/{report['mapped_underlying_count']} current"
    )

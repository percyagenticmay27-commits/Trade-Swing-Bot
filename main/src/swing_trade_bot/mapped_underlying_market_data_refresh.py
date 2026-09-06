"""Refresh read-only daily OHLCV evidence for the persistent mapped universe."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .data_download import build_historical_data
from .leveraged_vehicle_registry import preferred_vehicle_mapping

OUTPUT_NAME = "mapped_underlying_market_data_refresh.json"


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


def write_mapped_underlying_market_data_refresh(
    payload: Mapping[str, Any], *, output_dir: str | Path = "results"
) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / OUTPUT_NAME
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=root) as handle:
        json.dump(dict(payload), handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return path


def refresh_and_write_mapped_underlying_market_data(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    data_dir: str | Path = "data",
    output_dir: str | Path = "results",
    years: int = 5,
    refresh: bool = True,
) -> dict[str, Any]:
    payload = refresh_mapped_underlying_market_data(
        registry_path=registry_path,
        data_dir=data_dir,
        years=years,
        refresh=refresh,
    )
    write_mapped_underlying_market_data_refresh(payload, output_dir=output_dir)
    return payload


if __name__ == "__main__":
    report = refresh_and_write_mapped_underlying_market_data()
    print(
        "Mapped underlying market data refresh: "
        f"{report['current_market_data_count']}/{report['mapped_underlying_count']} current"
    )

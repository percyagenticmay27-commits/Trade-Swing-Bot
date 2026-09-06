"""Refresh read-only OHLCV evidence for current durable WATCHLIST vehicles.

This adapter bridges Tuesday Opportunity Quality selection into the existing daily
Swing timing engine without changing entry thresholds or creating positions.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .data_download import build_historical_data
from .enterprise_candidate_state import load_candidate_state

OUTPUT_NAME = "watchlist_vehicle_market_data_refresh.json"
BENCHMARKS = ("SPY", "QQQ")


def watchlist_vehicle_symbols(*, root: str | Path | None = None) -> tuple[str, ...]:
    candidates, _metadata = load_candidate_state(root=root)
    symbols = {
        (candidate.leveraged_symbol or "").strip().upper()
        for candidate in candidates
        if candidate.status == "WATCHLIST"
        and candidate.leveraged_vehicle_exists
        and (candidate.leveraged_symbol or "").strip()
    }
    return tuple(sorted(symbols))


def refresh_watchlist_vehicle_market_data(
    *,
    root: str | Path | None = None,
    data_dir: str | Path = "data",
    years: int = 5,
    refresh: bool = True,
) -> dict[str, Any]:
    """Refresh WATCHLIST vehicle + benchmark data with the existing provider chain."""
    base = Path(root) if root is not None else Path.cwd()
    vehicles = watchlist_vehicle_symbols(root=base)
    requested = tuple(dict.fromkeys((*vehicles, *BENCHMARKS)))
    run = build_historical_data(
        base / Path(data_dir),
        years=years,
        refresh=refresh,
        symbols=requested,
    )
    rows: list[dict[str, Any]] = []
    current = 0
    for summary in run.summaries:
        usable = bool(summary.rows) and summary.error is None and not summary.is_stale
        if usable:
            current += 1
        rows.append(
            {
                "symbol": summary.symbol,
                "role": "WATCHLIST_VEHICLE" if summary.symbol in vehicles else "BENCHMARK",
                "rows": summary.rows,
                "start_date": summary.start_date.isoformat() if summary.start_date else None,
                "end_date": summary.end_date.isoformat() if summary.end_date else None,
                "source": summary.source,
                "data_source": summary.data_source,
                "is_stale": summary.is_stale,
                "error": summary.error,
                "usable_for_entry_evaluation": usable,
            }
        )
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "source_authority": "DURABLE_SWING_WATCHLIST_STATE",
        "provider_policy": "EXISTING_READ_ONLY_MARKET_DATA_CHAIN",
        "watchlist_vehicle_count": len(vehicles),
        "watchlist_vehicles": list(vehicles),
        "benchmark_symbols": list(BENCHMARKS),
        "requested_symbol_count": len(requested),
        "current_market_data_count": current,
        "validation_ok": run.validation_ok,
        "rows": rows,
    }


def write_watchlist_vehicle_market_data_refresh(
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


def refresh_and_write_watchlist_vehicle_market_data(
    *,
    root: str | Path | None = None,
    data_dir: str | Path = "data",
    output_dir: str | Path = "results",
    years: int = 5,
    refresh: bool = True,
) -> dict[str, Any]:
    base = Path(root) if root is not None else Path.cwd()
    payload = refresh_watchlist_vehicle_market_data(
        root=base,
        data_dir=data_dir,
        years=years,
        refresh=refresh,
    )
    destination = base / Path(output_dir) if not Path(output_dir).is_absolute() else Path(output_dir)
    write_watchlist_vehicle_market_data_refresh(payload, output_dir=destination)
    return payload


if __name__ == "__main__":
    report = refresh_and_write_watchlist_vehicle_market_data()
    print(
        "Watchlist vehicle market data: "
        f"{report['watchlist_vehicle_count']} vehicles; "
        f"{report['current_market_data_count']}/{report['requested_symbol_count']} current"
    )

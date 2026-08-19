"""Evaluate current durable WATCHLIST vehicles with the existing Swing entry rules.

This module is timing evidence only. It never writes the paper ledger, creates a
position, places an order, or converts the existing entry rules into a new score.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .config import StrategyConfig
from .engine import SwingTradeEngine
from .enterprise_candidate_state import load_candidate_state
from .paper_runner import load_csv
from .user_veto_control import DEFAULT_LEDGER_PATH, active_vetoes, load_veto_ledger

OUTPUT_JSON = "watchlist_entry_evaluation.json"
OUTPUT_CSV = "watchlist_entry_evaluation.csv"


def _load_earnings_dates(path: Path) -> dict[str, date]:
    """Load known underlying earnings dates from the existing report when available."""
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", []) if isinstance(payload, Mapping) else []
    result: dict[str, date] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol", row.get("underlying_symbol", ""))).strip().upper()
        raw = str(row.get("earnings_date", "")).strip()
        if not symbol or not raw:
            continue
        try:
            result[symbol] = date.fromisoformat(raw)
        except ValueError:
            continue
    return result


def evaluate_watchlist_entries(
    *,
    root: str | Path | None = None,
    data_dir: str | Path = "data",
    earnings_report_path: str | Path = "results/earnings_report.json",
    veto_ledger_path: str | Path = DEFAULT_LEDGER_PATH,
) -> dict[str, Any]:
    base = Path(root) if root is not None else Path.cwd()
    data_root = base / Path(data_dir) if not Path(data_dir).is_absolute() else Path(data_dir)
    earnings_path = base / Path(earnings_report_path) if not Path(earnings_report_path).is_absolute() else Path(earnings_report_path)
    veto_path = base / Path(veto_ledger_path) if not Path(veto_ledger_path).is_absolute() else Path(veto_ledger_path)

    candidates, _metadata = load_candidate_state(root=base)
    watchlist = [
        candidate for candidate in candidates
        if candidate.status == "WATCHLIST"
        and candidate.leveraged_vehicle_exists
        and (candidate.leveraged_symbol or "").strip()
    ]
    watchlist.sort(key=lambda item: item.underlying_symbol.upper())
    vetoed = set(active_vetoes(load_veto_ledger(veto_path)))
    earnings_dates = _load_earnings_dates(earnings_path)

    vehicles = tuple((candidate.leveraged_symbol or "").strip().upper() for candidate in watchlist)
    exposure_map = tuple(
        (candidate.underlying_symbol.strip().upper(), (candidate.leveraged_symbol or "").strip().upper())
        for candidate in watchlist
    )
    config = StrategyConfig(symbols=vehicles, underlying_exposure_map=exposure_map)
    engine = SwingTradeEngine(config=config, paper_trade_mode=True)

    benchmark_data: dict[str, Any] = {}
    for benchmark in ("SPY", "QQQ"):
        path = data_root / f"{benchmark}.csv"
        if path.is_file():
            benchmark_data[benchmark] = load_csv(path)

    rows: list[dict[str, Any]] = []
    entry_ready_count = 0
    for candidate in watchlist:
        underlying = candidate.underlying_symbol.strip().upper()
        vehicle = (candidate.leveraged_symbol or "").strip().upper()
        if underlying in vetoed or vehicle in vetoed:
            rows.append({
                "underlying_symbol": underlying,
                "vehicle_symbol": vehicle,
                "lifecycle_status": candidate.status,
                "evaluation_status": "VETO_BLOCKED",
                "entry_ready": False,
                "engine_signal": None,
                "reason": "Active user veto blocks current-cycle progression",
                "earnings_date_known": underlying in earnings_dates,
                "paper_position_created": False,
            })
            continue

        vehicle_path = data_root / f"{vehicle}.csv"
        if not vehicle_path.is_file():
            rows.append({
                "underlying_symbol": underlying,
                "vehicle_symbol": vehicle,
                "lifecycle_status": candidate.status,
                "evaluation_status": "MISSING_MARKET_DATA",
                "entry_ready": False,
                "engine_signal": None,
                "reason": f"Missing current vehicle history: {vehicle_path}",
                "earnings_date_known": underlying in earnings_dates,
                "paper_position_created": False,
            })
            continue

        try:
            bars = load_csv(vehicle_path)
            result = engine.evaluate(
                vehicle,
                bars,
                benchmark_data=benchmark_data,
                earnings_dates=earnings_dates,
            )
        except (OSError, ValueError) as exc:
            rows.append({
                "underlying_symbol": underlying,
                "vehicle_symbol": vehicle,
                "lifecycle_status": candidate.status,
                "evaluation_status": "EVIDENCE_ERROR",
                "entry_ready": False,
                "engine_signal": None,
                "reason": f"{type(exc).__name__}: {exc}",
                "earnings_date_known": underlying in earnings_dates,
                "paper_position_created": False,
            })
            continue

        ready = result.signal == "BUY"
        if ready:
            entry_ready_count += 1
        rows.append({
            "underlying_symbol": underlying,
            "vehicle_symbol": vehicle,
            "lifecycle_status": candidate.status,
            "evaluation_status": "ENTRY_READY" if ready else "WAIT",
            "entry_ready": ready,
            "engine_signal": result.signal,
            "reason": result.reason,
            "current_price": result.current_price,
            "earnings_date_known": underlying in earnings_dates,
            "paper_position_created": False,
        })

    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "timing_authority": "EXISTING_SWING_TRADE_ENGINE",
        "entry_rules_changed": False,
        "numeric_entry_score_invented": False,
        "evaluation_scope": "DURABLE_WATCHLIST_VEHICLES_ONLY",
        "watchlist_vehicle_count": len(watchlist),
        "entry_ready_count": entry_ready_count,
        "paper_positions_created": 0,
        "paper_ledger_written": False,
        "earnings_evidence_available": earnings_path.is_file(),
        "rows": rows,
    }


def write_watchlist_entry_evaluation(
    payload: Mapping[str, Any], *, output_dir: str | Path = "results"
) -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / OUTPUT_JSON
    csv_path = root / OUTPUT_CSV
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=root) as handle:
        json.dump(dict(payload), handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, json_path)

    rows = list(payload.get("rows", []))
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False, dir=root) as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, csv_path)
    return json_path, csv_path


def build_and_write_watchlist_entry_evaluation(
    *,
    root: str | Path | None = None,
    data_dir: str | Path = "data",
    output_dir: str | Path = "results",
) -> dict[str, Any]:
    base = Path(root) if root is not None else Path.cwd()
    payload = evaluate_watchlist_entries(root=base, data_dir=data_dir)
    destination = base / Path(output_dir) if not Path(output_dir).is_absolute() else Path(output_dir)
    write_watchlist_entry_evaluation(payload, output_dir=destination)
    return payload


if __name__ == "__main__":
    report = build_and_write_watchlist_entry_evaluation()
    print(
        "Watchlist entry evaluation: "
        f"{report['watchlist_vehicle_count']} evaluated; "
        f"{report['entry_ready_count']} entry-ready"
    )

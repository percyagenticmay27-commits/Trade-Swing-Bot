"""Refresh authoritative paper evidence after frozen DIRECT Primary execution.

This module is deliberately narrow. It rebuilds portfolio valuation, the current
portfolio CSV adapter, managed trade history, and performance analytics from the
paper ledger after a frozen Primary BUY/SELL. It does not generate signals,
change strategy assignments, place broker orders, or move real capital.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .enterprise_strategy_allocation_discovery import (
    load_discovered_strategy_allocations,
    resolve_strategy_allocation_evidence,
)
from .paper_portfolio_manager import build_and_write_paper_portfolio_report
from .performance_analytics_engine import build_and_write_performance_analytics_report
from .trade_history_manager import build_and_write_trade_history_report

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
DEFAULT_CYCLE_CONFIG_PATH = Path("configs/swing_daily_cycle.json")
DEFAULT_LEDGER_DIR = Path("results/paper_ledger")
DEFAULT_DATA_DIR = Path("data")
PLUGIN_ID = "SWING-001"


def refresh_frozen_primary_post_execution_evidence(
    *,
    cycle_config_path: Path = DEFAULT_CYCLE_CONFIG_PATH,
    repository_root: Path = Path("."),
    as_of: date | None = None,
) -> dict[str, Any]:
    """Rebuild paper ledger evidence after a frozen Primary ledger mutation."""
    root = Path(repository_root).resolve()
    config = _load_object(root / cycle_config_path)
    refresh = config.get("runtime_evidence_refresh")
    if not isinstance(refresh, Mapping) or refresh.get("enabled") is not True:
        raise ValueError("runtime_evidence_refresh must be enabled")
    ledger_cfg = refresh.get("paper_ledger")
    if not isinstance(ledger_cfg, Mapping):
        raise ValueError("runtime_evidence_refresh.paper_ledger is required")

    ledger_dir = root / str(ledger_cfg.get("ledger_dir", DEFAULT_LEDGER_DIR))
    data_dir = root / str(ledger_cfg.get("data_dir", DEFAULT_DATA_DIR))
    if not (ledger_dir / "open_positions.json").is_file():
        raise FileNotFoundError(ledger_dir / "open_positions.json")
    if not (ledger_dir / "trade_history.json").is_file():
        raise FileNotFoundError(ledger_dir / "trade_history.json")

    allocations_payload, allocation_source_path = load_discovered_strategy_allocations()
    allocation_evidence = resolve_strategy_allocation_evidence(allocations_payload, PLUGIN_ID)
    account_capital = float(allocation_evidence["allocated_capital"])
    if account_capital <= 0:
        raise ValueError("Governed SWING-001 allocation must be positive")

    max_price_age_days = int(ledger_cfg.get("max_price_age_days", 5))
    report = build_and_write_paper_portfolio_report(
        ledger_dir=ledger_dir,
        data_dir=data_dir,
        output_dir=ledger_dir,
        account_capital=account_capital,
        as_of=as_of or date.today(),
        max_price_age_days=max_price_age_days,
    )
    summary_path = ledger_dir / "paper_portfolio_summary.json"
    positions_path = ledger_dir / "paper_portfolio_positions.json"
    summary = _load_object(summary_path)
    summary.update(
        {
            "strategy_id": PLUGIN_ID,
            "account_capital_source": "AI_CIO_ENTERPRISE_EVIDENCE",
            "account_capital_source_path": str(Path(allocation_source_path).resolve()),
            "account_capital_source_json_path": allocation_evidence.get("allocation_source_json_path"),
            "account_capital_evidence_schema": allocation_evidence.get("allocation_evidence_schema"),
        }
    )
    _atomic_json(summary_path, summary)
    current_csv = _write_current_portfolio_csv(
        positions_path,
        ledger_dir / "current_portfolio_positions.csv",
    )

    history = build_and_write_trade_history_report(
        trade_history_path=ledger_dir / "trade_history.json",
        output_dir=ledger_dir,
        data_dir=data_dir,
    )
    performance = build_and_write_performance_analytics_report(
        ledger_dir=ledger_dir,
        output_dir=ledger_dir,
    )

    return {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "account_capital": account_capital,
        "position_count": report.position_count,
        "closed_trade_count": history.closed_trade_count,
        "total_pnl": performance.total_pnl,
        "current_portfolio_positions_path": str(current_csv),
    }


def _write_current_portfolio_csv(positions_path: Path, destination: Path) -> Path:
    payload = _load_object(positions_path)
    if payload.get("paper_trade_mode") is not True:
        raise ValueError("paper_portfolio_positions.paper_trade_mode must be true")
    rows = payload.get("positions")
    if not isinstance(rows, list):
        raise ValueError("paper_portfolio_positions.json must contain a positions list")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["symbol", "shares", "market_value", "cost_basis"])
            writer.writeheader()
            for row in rows:
                if not isinstance(row, Mapping):
                    raise ValueError("paper portfolio position rows must be objects")
                writer.writerow(
                    {
                        "symbol": str(row.get("symbol", "")).strip().upper(),
                        "shares": row.get("shares"),
                        "market_value": row.get("market_value"),
                        "cost_basis": row.get("cost_basis"),
                    }
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return destination


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

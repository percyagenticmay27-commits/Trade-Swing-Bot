"""Operational paper-only workflow for frozen Primary/Shadow strategy stacks.

The workflow loads frozen symbol assignments, resolves timestamped NY-session
intraday data, simulates the DIRECT Primary and all active SHADOWS with the exact
same persistent Primary reference share quantity, and publishes research
evidence. The reference quantity survives periods when the DIRECT Primary is
flat, so Shadow comparisons do not stop after a Primary exit. It does not place
orders, create paper positions, reserve/move capital, or promote strategies.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, load_frozen_symbol_stacks
from .frozen_strategy_shadow_runtime import run_frozen_shadow_spec

DEFAULT_INTRADAY_DATA_DIR = Path("data/intraday")
DEFAULT_PRIMARY_POSITIONS_PATH = Path("results/frozen_primary_reference_positions.csv")
DEFAULT_PERFORMANCE_PATH = Path("results/frozen_strategy_performance.json")
DEFAULT_LEDGER_PATH = Path("results/frozen_strategy_ledger.json")
INTRADAY_DATA_DIR_ENV = "SWING_INTRADAY_DATA_DIR"

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
PAPER_POSITION_CREATION_ENABLED = False
AUTO_PROMOTION_ENABLED = False
SHADOW_ALLOCATION_MODEL = "SAME_PRIMARY_SHARE_QUANTITY_SIMULATED_ONLY"


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2)
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
    return path


def _intraday_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    raw = os.environ.get(INTRADAY_DATA_DIR_ENV, "").strip()
    return Path(raw) if raw else DEFAULT_INTRADAY_DATA_DIR


def _strategy_row(symbol: str, assignment_mode: str, result: Mapping[str, Any]) -> dict[str, Any]:
    performance = result.get("performance")
    if isinstance(performance, Mapping):
        row = dict(performance)
        row["underlying_symbol"] = symbol
        row["assignment_mode"] = assignment_mode
        row["evidence_status"] = str(performance.get("evidence_status", "AVAILABLE"))
        return row
    return {
        "underlying_symbol": symbol,
        "strategy_id": str(result.get("strategy_id", "")),
        "assignment_mode": assignment_mode,
        "evidence_status": str(result.get("evidence_status", "UNAVAILABLE")),
        **({"error": result["error"]} if result.get("error") else {}),
    }


def build_frozen_strategy_evidence(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    intraday_data_dir: Path | None = None,
    primary_positions_path: Path = DEFAULT_PRIMARY_POSITIONS_PATH,
) -> dict[str, Any]:
    """Run every frozen DIRECT/SHADOW assignment using persistent Primary shares."""
    data_dir = _intraday_dir(intraday_data_dir)
    rows: list[dict[str, Any]] = []
    ledger_rows: list[dict[str, Any]] = []

    for stack in load_frozen_symbol_stacks(config_path):
        signal_path = data_dir / f"{stack.symbol}.csv"
        vehicle_path = data_dir / f"{stack.symbol}.csv"
        for spec in (stack.primary, *stack.shadows):
            result = run_frozen_shadow_spec(
                spec,
                signal_intraday_path=signal_path,
                vehicle_intraday_path=vehicle_path,
                primary_positions_path=primary_positions_path,
            )
            rows.append(_strategy_row(stack.symbol, spec.assignment_mode, result))
            for event in result.get("ledger_rows", []):
                if isinstance(event, Mapping):
                    ledger_rows.append({"underlying_symbol": stack.symbol, "assignment_mode": spec.assignment_mode, **dict(event)})

    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "paper_positions_created": 0,
        "auto_promotion_enabled": False,
        "shadow_allocation_model": SHADOW_ALLOCATION_MODEL,
        "intraday_data_dir": str(data_dir),
        "primary_quantity_authority": str(primary_positions_path),
        "rows": rows,
        "ledger_rows": ledger_rows,
    }


def build_and_write_frozen_strategy_evidence(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    intraday_data_dir: Path | None = None,
    primary_positions_path: Path = DEFAULT_PRIMARY_POSITIONS_PATH,
    performance_path: Path = DEFAULT_PERFORMANCE_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> dict[str, Any]:
    payload = build_frozen_strategy_evidence(
        config_path=config_path,
        intraday_data_dir=intraday_data_dir,
        primary_positions_path=primary_positions_path,
    )
    performance_payload = {key: value for key, value in payload.items() if key != "ledger_rows"}
    ledger_payload = {
        "schema_version": payload["schema_version"],
        "strategy_id": payload["strategy_id"],
        "paper_trade_mode": True,
        "shadow_allocation_model": SHADOW_ALLOCATION_MODEL,
        "rows": payload["ledger_rows"],
    }
    _atomic_json(performance_path, performance_payload)
    _atomic_json(ledger_path, ledger_payload)
    return payload

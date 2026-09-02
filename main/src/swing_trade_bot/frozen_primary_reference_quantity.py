"""Persist exact frozen Primary reference share quantities for Shadow research.

The current paper portfolio may be flat after a DIRECT Primary exit. Shadows still
need the same strategy-comparison position size that the Primary allocation last
carried, otherwise Shadow evidence would disappear precisely while the Primary is
out of market. This module snapshots the latest observed Primary share quantity
for each frozen symbol and preserves it while that symbol is temporarily flat.

It is paper/research-only: it does not create positions, move capital, place
orders, or change strategy authority.
"""
from __future__ import annotations

import csv
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from .frozen_strategy_assignment_registry import DEFAULT_CONFIG_PATH, load_frozen_symbol_stacks

PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False
PAPER_POSITION_CREATION_ENABLED = False
DEFAULT_CURRENT_POSITIONS_PATH = Path("results/paper_ledger/current_portfolio_positions.csv")
DEFAULT_REFERENCE_PATH = Path("results/frozen_primary_reference_positions.csv")


def refresh_frozen_primary_reference_quantities(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    current_positions_path: Path = DEFAULT_CURRENT_POSITIONS_PATH,
    reference_path: Path = DEFAULT_REFERENCE_PATH,
) -> dict[str, Any]:
    """Refresh last-known allocated shares for frozen symbols without erasing flats."""
    symbols = {stack.symbol for stack in load_frozen_symbol_stacks(config_path)}
    prior = _read_positions(reference_path, missing_ok=True)
    current = _read_positions(current_positions_path, missing_ok=True)

    merged: dict[str, dict[str, float | str]] = {
        symbol: row for symbol, row in prior.items() if symbol in symbols
    }
    rows: list[dict[str, Any]] = []
    for symbol in sorted(symbols):
        live = current.get(symbol)
        if live is not None:
            merged[symbol] = live
            status = "UPDATED_FROM_OPEN_PRIMARY"
        elif symbol in merged:
            status = "PRESERVED_WHILE_PRIMARY_FLAT"
        else:
            status = "MISSING_REFERENCE_QUANTITY"
        row = merged.get(symbol)
        rows.append({
            "symbol": symbol,
            "status": status,
            "shares": None if row is None else row["shares"],
            "cost_basis": None if row is None else row["cost_basis"],
            "market_value": None if row is None else row["market_value"],
        })

    _atomic_csv(reference_path, [merged[symbol] for symbol in sorted(merged)])
    return {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "paper_positions_created": 0,
        "reference_path": str(reference_path),
        "rows": rows,
    }


def _read_positions(path: Path, *, missing_ok: bool) -> dict[str, dict[str, float | str]]:
    if not path.is_file():
        if missing_ok:
            return {}
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return {}
        names = {name.strip().lower(): name for name in reader.fieldnames}
        required = {"symbol", "shares", "market_value", "cost_basis"}
        if not required.issubset(names):
            raise ValueError(f"{path} must contain symbol, shares, market_value, cost_basis")
        output: dict[str, dict[str, float | str]] = {}
        for raw in reader:
            symbol = str(raw[names["symbol"]]).strip().upper()
            if not symbol:
                raise ValueError("position symbol is required")
            if symbol in output:
                raise ValueError(f"duplicate position row for {symbol}")
            shares = _positive(raw[names["shares"]], f"{symbol}.shares")
            market_value = _nonnegative(raw[names["market_value"]], f"{symbol}.market_value")
            cost_basis = _positive(raw[names["cost_basis"]], f"{symbol}.cost_basis")
            output[symbol] = {
                "symbol": symbol,
                "shares": shares,
                "market_value": market_value,
                "cost_basis": cost_basis,
            }
        return output


def _positive(value: Any, field: str) -> float:
    number = _nonnegative(value, field)
    if number <= 0:
        raise ValueError(f"{field} must be positive")
    return number


def _nonnegative(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return number


def _atomic_csv(path: Path, rows: list[dict[str, float | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["symbol", "shares", "market_value", "cost_basis"])
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

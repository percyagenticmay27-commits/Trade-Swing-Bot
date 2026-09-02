"""Paper-only registry for frozen Primary/Shadow strategy stacks.

This registry is separate from the legacy declarative manual-strategy registry.
It stores only exact frozen-engine specifications and preserves one DIRECT
Primary plus up to three SHADOW strategies per symbol. Capital allocation,
promotion qualification, veto lifecycle, and brokerage execution remain outside
this module.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .frozen_strategy_shadow_runtime import FrozenStrategySpec

DEFAULT_CONFIG_PATH = Path("configs/frozen_strategy_assignments.json")
MAX_SHADOWS = 3
PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
ORDER_PLACEMENT_ENABLED = False
CAPITAL_MOVEMENT_ENABLED = False


@dataclass(frozen=True, slots=True)
class FrozenSymbolStack:
    symbol: str
    primary: FrozenStrategySpec
    shadows: tuple[FrozenStrategySpec, ...]
    shadow_slot_3_empty: bool
    research_status: str

    def __post_init__(self) -> None:
        if self.symbol != self.symbol.strip().upper() or not self.symbol:
            raise ValueError("symbol must be uppercase and trimmed")
        if self.primary.assignment_mode != "DIRECT":
            raise ValueError("primary strategy must be DIRECT")
        if self.primary.signal_symbol != self.symbol or self.primary.vehicle_symbol != self.symbol:
            raise ValueError("frozen direct ETF stack must use its symbol for signal and vehicle")
        if len(self.shadows) > MAX_SHADOWS:
            raise ValueError("a frozen stack may contain at most three shadows")
        if any(item.assignment_mode != "SHADOW" for item in self.shadows):
            raise ValueError("all shadow strategies must use SHADOW assignment_mode")
        if any(item.signal_symbol != self.symbol or item.vehicle_symbol != self.symbol for item in self.shadows):
            raise ValueError("frozen ETF shadows must use the stack symbol for signal and vehicle")
        ids = [self.primary.strategy_id, *(item.strategy_id for item in self.shadows)]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate strategy IDs are not allowed within a frozen stack")


def _spec(raw: Mapping[str, Any]) -> FrozenStrategySpec:
    params = raw.get("parameters", {})
    if not isinstance(params, Mapping):
        raise ValueError("strategy parameters must be an object")
    return FrozenStrategySpec(
        strategy_id=str(raw["strategy_id"]).strip().upper(),
        name=str(raw["name"]),
        signal_symbol=str(raw["signal_symbol"]).strip().upper(),
        vehicle_symbol=str(raw["vehicle_symbol"]).strip().upper(),
        timeframe=str(raw["timeframe"]).strip().upper(),
        engine_id=str(raw["engine_id"]).strip().upper(),
        parameters=dict(params),
        catastrophic_stop_percent=None if raw.get("catastrophic_stop_percent") is None else float(raw["catastrophic_stop_percent"]),
        assignment_mode=str(raw.get("assignment_mode", "SHADOW")).strip().upper(),
        enabled=bool(raw.get("enabled", True)),
        paper_trade_mode=bool(raw.get("paper_trade_mode", True)),
    )


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("frozen strategy registry root must be an object")
    if payload.get("strategy_id") != "SWING-001" or payload.get("paper_trade_mode") is not True:
        raise ValueError("frozen strategy registry must be authoritative SWING-001 paper configuration")
    return payload


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


def load_frozen_symbol_stacks(path: Path = DEFAULT_CONFIG_PATH) -> tuple[FrozenSymbolStack, ...]:
    payload = _load_payload(path)
    strategy_rows = payload.get("strategies", [])
    symbol_rows = payload.get("symbols", [])
    if not isinstance(strategy_rows, list) or not isinstance(symbol_rows, list):
        raise ValueError("strategies and symbols must be lists")
    specs = {_spec(raw).strategy_id: _spec(raw) for raw in strategy_rows if isinstance(raw, Mapping)}
    stacks: list[FrozenSymbolStack] = []
    seen_symbols: set[str] = set()
    for raw in symbol_rows:
        if not isinstance(raw, Mapping):
            raise ValueError("symbol stack must be an object")
        symbol = str(raw["symbol"]).strip().upper()
        if symbol in seen_symbols:
            raise ValueError(f"duplicate frozen symbol stack: {symbol}")
        seen_symbols.add(symbol)
        primary_id = str(raw["primary_strategy_id"]).strip().upper()
        shadow_ids_raw = raw.get("shadow_strategy_ids", [])
        if not isinstance(shadow_ids_raw, list):
            raise ValueError("shadow_strategy_ids must be a list")
        shadow_ids = [str(value).strip().upper() for value in shadow_ids_raw]
        if len(shadow_ids) > MAX_SHADOWS:
            raise ValueError("at most three active shadows are allowed")
        try:
            primary = specs[primary_id]
            shadows = tuple(specs[item] for item in shadow_ids)
        except KeyError as exc:
            raise ValueError(f"unknown frozen strategy ID: {exc.args[0]}") from exc
        stacks.append(FrozenSymbolStack(
            symbol=symbol,
            primary=primary,
            shadows=shadows,
            shadow_slot_3_empty=raw.get("shadow_slot_3") is None and len(shadows) < 3,
            research_status=str(raw.get("research_status", "")),
        ))
    return tuple(stacks)


def resolve_frozen_stack(symbol: str, path: Path = DEFAULT_CONFIG_PATH) -> FrozenSymbolStack | None:
    target = symbol.strip().upper()
    for stack in load_frozen_symbol_stacks(path):
        if stack.symbol == target:
            return stack
    return None


def promote_frozen_shadow(
    *,
    symbol: str,
    strategy_id: str,
    path: Path = DEFAULT_CONFIG_PATH,
) -> str:
    """Swap one qualified frozen SHADOW into DIRECT and demote the old Primary.

    This mutates strategy authority only. Existing portfolio capital and share
    quantity are untouched, and no paper position, order, or broker action occurs.
    The old Primary replaces the promoted Shadow in the same shadow slot so the
    active shadow count and deterministic ordering are preserved.
    """
    target_symbol = symbol.strip().upper()
    target_strategy = strategy_id.strip().upper()
    if not target_symbol or not target_strategy:
        raise ValueError("symbol and strategy_id are required")
    payload = _load_payload(path)
    symbols = payload.get("symbols")
    strategies = payload.get("strategies")
    if not isinstance(symbols, list) or not isinstance(strategies, list):
        raise ValueError("strategies and symbols must be lists")

    stack_row: dict[str, Any] | None = None
    for raw in symbols:
        if isinstance(raw, dict) and str(raw.get("symbol", "")).strip().upper() == target_symbol:
            stack_row = raw
            break
    if stack_row is None:
        raise ValueError(f"no frozen stack for symbol {target_symbol}")

    previous_primary = str(stack_row.get("primary_strategy_id", "")).strip().upper()
    raw_shadow_ids = stack_row.get("shadow_strategy_ids", [])
    if not isinstance(raw_shadow_ids, list):
        raise ValueError("shadow_strategy_ids must be a list")
    shadow_ids = [str(value).strip().upper() for value in raw_shadow_ids]
    if target_strategy not in shadow_ids:
        raise ValueError(f"strategy {target_strategy} is not an active SHADOW for {target_symbol}")
    if previous_primary == target_strategy:
        raise ValueError("target strategy is already Primary")

    by_id = {
        str(raw.get("strategy_id", "")).strip().upper(): raw
        for raw in strategies
        if isinstance(raw, dict)
    }
    if previous_primary not in by_id or target_strategy not in by_id:
        raise ValueError("frozen strategy row missing for promotion swap")

    slot = shadow_ids.index(target_strategy)
    shadow_ids[slot] = previous_primary
    stack_row["primary_strategy_id"] = target_strategy
    stack_row["shadow_strategy_ids"] = shadow_ids
    by_id[previous_primary]["assignment_mode"] = "SHADOW"
    by_id[target_strategy]["assignment_mode"] = "DIRECT"

    updated = dict(payload)
    updated["symbols"] = symbols
    updated["strategies"] = strategies
    _atomic_json(path, updated)
    load_frozen_symbol_stacks(path)  # fail closed if the persisted swap violates registry invariants
    return previous_primary

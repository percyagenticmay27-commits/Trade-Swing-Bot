"""Paper-only registry for frozen Primary/Shadow strategy stacks.

This registry is separate from the legacy declarative manual-strategy registry.
It stores only exact frozen-engine specifications and preserves one DIRECT
Primary plus up to three SHADOW strategies per symbol. Capital allocation,
promotion qualification, veto lifecycle, and brokerage execution remain outside
this module.
"""
from __future__ import annotations

import json
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


def load_frozen_symbol_stacks(path: Path = DEFAULT_CONFIG_PATH) -> tuple[FrozenSymbolStack, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not bool(payload.get("paper_trade_mode", True)):
        raise ValueError("paper_trade_mode=True is mandatory")
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

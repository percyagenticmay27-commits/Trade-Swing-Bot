"""Host-readable contract for the SWING-001 manual entry-strategy form.

The Enterprise AI CIO may render this contract, but Swing remains the authority
for strategy validation and persistence. This module is paper-only and performs
no broker, order, position, SGOV, or capital movement operations.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .manual_entry_strategy_registry import (
    SUPPORTED_OPERATORS,
    SUPPORTED_SOURCES,
    SUPPORTED_TIMEFRAMES,
    load_manual_entry_strategy_registry,
)

SCHEMA_VERSION = "1.2"
STRATEGY_ID = "SWING-001"
DEFAULT_REGISTRY_PATH = Path("configs/manual_entry_strategies.json")
DEFAULT_OUTPUT_PATH = Path("results/manual_entry_strategy_form_contract.json")


def _strategy_payload(item: Any) -> dict[str, Any]:
    payload = asdict(item)
    payload["rules"] = [asdict(rule) for rule in item.rules]
    payload["regime_filters"] = [asdict(rule) for rule in item.regime_filters]
    return payload


def build_manual_entry_strategy_form_contract(
    *, registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    registry = load_manual_entry_strategy_registry(registry_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "form_id": "SWING_MANUAL_ENTRY_STRATEGY",
        "display_name": "Manual Strategy",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR",
        "assignment_authority": "UNDERLYING_SYMBOL",
        "execution_vehicle_authority": "VERIFIED_SWING_MAPPING",
        "persistence_authority": "SWING_MANUAL_ENTRY_STRATEGY_REGISTRY",
        "host_may_render": True,
        "host_may_write_strategy_storage_directly": False,
        "fields": [
            {
                "name": "strategy_id",
                "label": "Strategy ID",
                "type": "text",
                "required": True,
                "help": "Permanent machine-readable identifier for this strategy. Use letters, numbers, and underscores; keep it stable after saving.",
                "example": "NFLX_DAILY_KELTNER_V1",
            },
            {
                "name": "name",
                "label": "Strategy Name",
                "type": "text",
                "required": True,
                "help": "Friendly name shown to the user in reports and assignments.",
                "example": "NFLX Daily Keltner Entry",
            },
            {
                "name": "enabled",
                "label": "Enabled",
                "type": "boolean",
                "required": True,
                "default": True,
                "help": "Controls whether this strategy may be resolved for future entry evaluation. Disabling it does not place or close a trade.",
                "example": "Enabled",
            },
            {
                "name": "underlying_symbol",
                "label": "Underlying Symbol",
                "type": "symbol",
                "required": True,
                "help": "Ticker whose market data and indicators generate the entry signal. Enter the underlying company, not the leveraged vehicle.",
                "example": "NFLX",
            },
            {
                "name": "execution_symbol",
                "label": "Execution Vehicle",
                "type": "readonly_mapping",
                "required": False,
                "help": "Read-only leveraged vehicle resolved from Swing's verified mapping. The user cannot override it here.",
                "example": "NFLX → NFLU",
            },
            {
                "name": "direction",
                "label": "Direction",
                "type": "select",
                "required": True,
                "choices": ["LONG"],
                "help": "Trade direction supported by this manual-entry layer. Version 1 currently supports LONG only.",
                "example": "LONG",
            },
            {
                "name": "timeframe",
                "label": "Timeframe",
                "type": "select",
                "required": True,
                "choices": sorted(SUPPORTED_TIMEFRAMES),
                "help": "Chart/bar interval on which all entry and regime rules are evaluated.",
                "example": "1D",
            },
            {
                "name": "session",
                "label": "Session",
                "type": "text",
                "required": True,
                "default": "REGULAR_SESSION",
                "help": "Trading session whose bars are eligible for the strategy. For Daily stock strategies, REGULAR_SESSION is the normal choice.",
                "example": "REGULAR_SESSION",
            },
            {
                "name": "number_of_entries",
                "label": "Number of Entries",
                "type": "integer",
                "required": True,
                "minimum": 1,
                "default": 1,
                "help": "How many staged purchases are allowed. Swing divides its authorized allocation equally across this many entries; the final slice absorbs rounding.",
                "example": "2 means a $600 Swing allocation becomes two $300 entry slices",
            },
            {
                "name": "rule_logic",
                "label": "Entry Rule Logic",
                "type": "select",
                "required": True,
                "choices": ["ALL", "ANY"],
                "help": "ALL requires every entry rule to be true. ANY requires at least one entry rule to be true.",
                "example": "ALL",
            },
            {
                "name": "rules",
                "label": "Entry Rules",
                "type": "rule_list",
                "required": True,
                "source_choices": sorted(SUPPORTED_SOURCES),
                "operator_choices": sorted(SUPPORTED_OPERATORS),
                "help": "Conditions that trigger an entry stage. Enter a left source/indicator, comparison operator, right value or indicator, and an indicator period when needed.",
                "example": "close > ema, period 20; RSI between 45,65, period 14",
            },
            {
                "name": "confirmation",
                "label": "Confirmation",
                "type": "structured_optional",
                "required": False,
                "help": "Optional persistence requirement before entry qualifies, such as requiring the setup to remain true for consecutive bars.",
                "example": "2 consecutive qualifying Daily closes",
            },
            {
                "name": "regime_logic",
                "label": "Regime Filter Logic",
                "type": "select",
                "required": False,
                "choices": ["ALL", "ANY"],
                "default": "ALL",
                "help": "Controls how multiple market/regime filters are combined. ALL is the safer default.",
                "example": "ALL",
            },
            {
                "name": "regime_filters",
                "label": "Regime Filters",
                "type": "rule_list",
                "required": False,
                "source_choices": sorted(SUPPORTED_SOURCES),
                "operator_choices": sorted(SUPPORTED_OPERATORS),
                "storage": "STRUCTURED_LIST_NOT_COMMA_STRING",
                "help": "Optional conditions that describe the market environment required before entry rules may act. Add each filter as its own structured row.",
                "example": "CHOP(14) < 60; market_filter == satisfied",
            },
            {
                "name": "exit_policy_id",
                "label": "Exit Policy",
                "type": "reference",
                "required": False,
                "help": "Optional reference to an existing Swing exit-management policy. This form does not redefine the exit engine.",
                "example": "TIERED_TRAILING",
            },
            {
                "name": "reentry_cooldown",
                "label": "Re-entry Cooldown / Reset",
                "type": "structured_optional",
                "required": False,
                "help": "Optional wait/reset requirement after an exit before the strategy may start a new entry cycle.",
                "example": "1 bar",
            },
            {
                "name": "allocation_authority",
                "label": "Allocation Authority",
                "type": "readonly",
                "value": "SWING_PORTFOLIO_ALLOCATOR",
                "help": "Read-only. Swing decides the total dollars allocated to the opportunity; the manual strategy never sets position dollars.",
                "example": "SWING_PORTFOLIO_ALLOCATOR",
            },
            {
                "name": "paper_trade_mode",
                "label": "Paper Only",
                "type": "readonly",
                "value": True,
                "help": "Mandatory safety mode. Manual strategy entry cannot enable live trading or broker execution.",
                "example": "TRUE",
            },
        ],
        "current_registry": {
            "default_strategy_id": registry.default_strategy_id,
            "strategies": [_strategy_payload(item) for item in registry.strategies],
            "assignments": [asdict(item) for item in registry.assignments],
        },
        "submission_contract": {
            "mode": "SWING_VALIDATED_INTAKE",
            "host_direct_file_write_allowed": False,
            "paper_only": True,
            "status": "AVAILABLE",
            "handler_module": "swing_trade_bot.manual_entry_strategy_intake",
            "handler_function": "apply_manual_entry_strategy_submission",
            "host_route": "/strategy/manual-entry",
            "host_transport": "LOCAL_SWING_CLI_STDIN_JSON",
            "allocation_fields_user_writable": False,
            "execution_vehicle_user_writable": False,
        },
    }


def write_manual_entry_strategy_form_contract(
    payload: dict[str, Any], *, output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return output_path


def build_and_write_manual_entry_strategy_form_contract(
    *, registry_path: Path = DEFAULT_REGISTRY_PATH, output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    payload = build_manual_entry_strategy_form_contract(registry_path=registry_path)
    write_manual_entry_strategy_form_contract(payload, output_path=output_path)
    return payload


if __name__ == "__main__":
    result = build_and_write_manual_entry_strategy_form_contract()
    print(
        "Manual strategy form contract: "
        f"{len(result['current_registry']['strategies'])} strategies; "
        f"{len(result['current_registry']['assignments'])} assignments"
    )

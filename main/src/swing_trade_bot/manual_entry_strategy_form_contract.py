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

SCHEMA_VERSION = "1.1"
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
            {"name": "strategy_id", "label": "Strategy ID", "type": "text", "required": True},
            {"name": "name", "label": "Strategy Name", "type": "text", "required": True},
            {"name": "enabled", "label": "Enabled", "type": "boolean", "required": True, "default": True},
            {"name": "underlying_symbol", "label": "Underlying Symbol", "type": "symbol", "required": True},
            {"name": "execution_symbol", "label": "Execution Vehicle", "type": "readonly_mapping", "required": False},
            {"name": "direction", "label": "Direction", "type": "select", "required": True, "choices": ["LONG"]},
            {"name": "timeframe", "label": "Timeframe", "type": "select", "required": True, "choices": sorted(SUPPORTED_TIMEFRAMES)},
            {"name": "session", "label": "Session", "type": "text", "required": True, "default": "REGULAR_SESSION"},
            {"name": "number_of_entries", "label": "Number of Entries", "type": "integer", "required": True, "minimum": 1, "default": 1, "help": "Swing divides its authorized allocation equally across this many entries; the final slice absorbs rounding."},
            {"name": "rule_logic", "label": "Entry Rule Logic", "type": "select", "required": True, "choices": ["ALL", "ANY"]},
            {"name": "rules", "label": "Entry Rules", "type": "rule_list", "required": True, "source_choices": sorted(SUPPORTED_SOURCES), "operator_choices": sorted(SUPPORTED_OPERATORS)},
            {"name": "confirmation", "label": "Confirmation", "type": "structured_optional", "required": False},
            {"name": "regime_logic", "label": "Regime Filter Logic", "type": "select", "required": False, "choices": ["ALL", "ANY"], "default": "ALL"},
            {"name": "regime_filters", "label": "Regime Filters", "type": "rule_list", "required": False, "source_choices": sorted(SUPPORTED_SOURCES), "operator_choices": sorted(SUPPORTED_OPERATORS), "storage": "STRUCTURED_LIST_NOT_COMMA_STRING"},
            {"name": "exit_policy_id", "label": "Exit Policy", "type": "reference", "required": False},
            {"name": "reentry_cooldown", "label": "Re-entry Cooldown / Reset", "type": "structured_optional", "required": False},
            {"name": "allocation_authority", "label": "Allocation Authority", "type": "readonly", "value": "SWING_PORTFOLIO_ALLOCATOR"},
            {"name": "paper_trade_mode", "label": "Paper Only", "type": "readonly", "value": True},
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
            "status": "INTAKE_HANDLER_AVAILABLE",
            "handler_module": "swing_trade_bot.manual_entry_strategy_intake",
            "handler_function": "apply_manual_entry_strategy_submission",
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

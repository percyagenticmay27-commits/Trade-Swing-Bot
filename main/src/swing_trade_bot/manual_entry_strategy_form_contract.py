"""Host-readable contract for the SWING-001 manual trading-strategy form.

The Enterprise AI CIO may render this contract, but Swing remains the authority
for validation and persistence. This module is paper-only and performs no broker,
order, position, SGOV, or capital-movement operations.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .manual_entry_strategy_registry import (
    SUPPORTED_ASSIGNMENT_MODES,
    SUPPORTED_OPERATORS,
    SUPPORTED_PRICE_SOURCES,
    SUPPORTED_SMOOTHING,
    SUPPORTED_SOURCES,
    SUPPORTED_TIMEFRAMES,
    load_manual_entry_strategy_registry,
)

SCHEMA_VERSION = "1.4"
STRATEGY_ID = "SWING-001"
DEFAULT_REGISTRY_PATH = Path("configs/manual_entry_strategies.json")
DEFAULT_OUTPUT_PATH = Path("results/manual_entry_strategy_form_contract.json")


def _strategy_payload(item: Any) -> dict[str, Any]:
    return asdict(item)


def _rule_field(name: str, label: str, *, required: bool, help_text: str, example: str) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": "rule_list",
        "required": required,
        "source_choices": sorted(SUPPORTED_SOURCES),
        "operator_choices": sorted(SUPPORTED_OPERATORS),
        "smoothing_choices": sorted(SUPPORTED_SMOOTHING),
        "price_source_choices": sorted(SUPPORTED_PRICE_SOURCES),
        "parameter_columns": ["period", "factor", "smoothing", "price_source"],
        "help": help_text,
        "example": example,
    }


def build_manual_entry_strategy_form_contract(*, registry_path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    registry = load_manual_entry_strategy_registry(registry_path)
    fields = [
        {"name": "strategy_id", "label": "Strategy ID", "type": "text", "required": True,
         "help": "Permanent machine-readable identifier. Keep it stable after saving.", "example": "M_HMA50_DAILY"},
        {"name": "name", "label": "Strategy Name", "type": "text", "required": True,
         "help": "Friendly name shown in reports and assignments.", "example": "M-HMA50 Daily"},
        {"name": "enabled", "label": "Enabled", "type": "boolean", "required": True, "default": True,
         "help": "Controls whether the strategy can be evaluated. It never places or closes a trade by itself.", "example": "Enabled"},
        {"name": "underlying_symbol", "label": "Underlying Symbol", "type": "symbol", "required": True,
         "help": "Ticker whose market data generates the strategy signal. Enter the underlying, not the leveraged vehicle.", "example": "NFLX"},
        {"name": "assignment_mode", "label": "Assignment Mode", "type": "select", "required": True,
         "choices": sorted(SUPPORTED_ASSIGNMENT_MODES), "default": "DIRECT",
         "help": "DIRECT is the active strategy. SHADOW is research-only and cannot reserve capital, move SGOV, create a paper position, or auto-promote.",
         "example": "DIRECT for NFLX M-HMA50; SHADOW for a challenger"},
        {"name": "execution_symbol", "label": "Execution Vehicle", "type": "readonly_mapping", "required": False,
         "help": "Read-only leveraged vehicle resolved from Swing's verified mapping.", "example": "NFLX → NFLU"},
        {"name": "direction", "label": "Direction", "type": "select", "required": True, "choices": ["LONG"],
         "help": "Trade direction supported by this manual layer.", "example": "LONG"},
        {"name": "timeframe", "label": "Timeframe", "type": "select", "required": True,
         "choices": sorted(SUPPORTED_TIMEFRAMES), "help": "Bar interval used by entry and exit rules.", "example": "1D"},
        {"name": "session", "label": "Session", "type": "text", "required": True, "default": "REGULAR_SESSION",
         "help": "Trading session used to construct/evaluate bars.", "example": "08:30-14:30 CT"},
        {"name": "number_of_entries", "label": "Number of Entries", "type": "integer", "required": True,
         "minimum": 1, "default": 1,
         "help": "How many staged purchases may occur. Swing divides its own authorized allocation equally across them.",
         "example": "1 for M-HMA50"},
        {"name": "rule_logic", "label": "Entry Rule Logic", "type": "select", "required": True,
         "choices": ["ALL", "ANY"], "help": "ALL requires every entry rule; ANY requires at least one.", "example": "ALL"},
        _rule_field(
            "rules", "Entry Rules", required=True,
            help_text="Conditions that define one qualifying entry bar. Indicator parameters are explicit so frozen setups are not approximated.",
            example="close > keltner_middle [period 14, factor 1, WILDER, OHLC_AVERAGE]; close > ema [period 14]",
        ),
        {"name": "confirmation_bars", "label": "Consecutive Qualifying Bars", "type": "integer", "required": True,
         "minimum": 1, "default": 1,
         "help": "The complete entry condition must remain true for this many consecutive completed bars before entry qualifies.",
         "example": "2 for M-HMA50 Daily"},
        {"name": "regime_logic", "label": "Regime Filter Logic", "type": "select", "required": False,
         "choices": ["ALL", "ANY"], "default": "ALL", "help": "Controls how multiple regime filters combine.", "example": "ALL"},
        _rule_field(
            "regime_filters", "Regime Filters", required=False,
            help_text="Optional environment requirements. Add each filter as a separate structured row.",
            example="chop < 60 [period 14]",
        ),
        {"name": "normal_exit_logic", "label": "Normal Exit Logic", "type": "select", "required": False,
         "choices": ["ALL", "ANY"], "default": "ANY",
         "help": "How always-active exit rules combine. ANY means any one failure condition can sell.", "example": "ANY"},
        _rule_field(
            "normal_exit_rules", "Normal Exit Rules", required=False,
            help_text="Always-active technical exit conditions evaluated while a position is open.",
            example="close < ema [period 18]; close < keltner_middle [period 14, factor 1, WILDER, OHLC_AVERAGE]",
        ),
        {"name": "conditional_exit_enabled", "label": "Conditional Exit", "type": "boolean", "required": False, "default": False,
         "help": "Enable an additional exit branch only after a position-state condition is satisfied.", "example": "Enabled for M-HMA50"},
        {"name": "conditional_exit_pl_threshold", "label": "Conditional Exit Profit Threshold ($)", "type": "number", "required": False,
         "default": 0, "help": "Conditional exit activates only when current position P/L is greater than this dollar amount.",
         "example": "0 means activate only when position P/L > $0"},
        _rule_field(
            "conditional_exit_rules", "Conditional Exit Rules", required=False,
            help_text="Exit rules evaluated only while the conditional profit gate is active.",
            example="close < hma [period 50]",
        ),
        {"name": "conditional_exit_cooldown_bars", "label": "Cooldown After Conditional Exit", "type": "integer", "required": False,
         "minimum": 0, "default": 0,
         "help": "Complete trading days/bars to wait after the conditional exit before entry can re-arm.",
         "example": "2 complete trading days for M-HMA50"},
        {"name": "conditional_exit_cooldown_unit", "label": "Cooldown Unit", "type": "select", "required": False,
         "choices": ["TRADING_DAY", "BAR"], "default": "TRADING_DAY",
         "help": "Unit used by the conditional-exit cooldown.", "example": "TRADING_DAY"},
        {"name": "exit_policy_id", "label": "Existing Exit Policy Reference", "type": "reference", "required": False,
         "help": "Optional reference to an existing Swing exit policy. Leave blank when defining exit rules directly above.", "example": "Leave blank for M-HMA50"},
        {"name": "allocation_authority", "label": "Allocation Authority", "type": "readonly", "value": "SWING_PORTFOLIO_ALLOCATOR",
         "help": "Read-only. Swing decides total dollars; the manual strategy never sets position dollars.", "example": "SWING_PORTFOLIO_ALLOCATOR"},
        {"name": "paper_trade_mode", "label": "Paper Only", "type": "readonly", "value": True,
         "help": "Mandatory safety mode. This form cannot enable live trading or broker execution.", "example": "TRUE"},
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "form_id": "SWING_MANUAL_TRADING_STRATEGY",
        "display_name": "Manual Strategy",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR",
        "shadow_allocation_model": "SAME_CURRENT_SWING_ALLOCATION_SIMULATED_ONLY",
        "assignment_authority": "UNDERLYING_SYMBOL",
        "assignment_modes": {
            "DIRECT": "One active strategy per underlying.",
            "SHADOW": "Multiple research-only strategies per underlying; no automatic promotion.",
        },
        "execution_vehicle_authority": "VERIFIED_SWING_MAPPING",
        "persistence_authority": "SWING_MANUAL_ENTRY_STRATEGY_REGISTRY",
        "host_may_render": True,
        "host_may_write_strategy_storage_directly": False,
        "fields": fields,
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
            "assignment_mode_user_writable": True,
        },
    }


def write_manual_entry_strategy_form_contract(payload: dict[str, Any], *, output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return output_path


def build_and_write_manual_entry_strategy_form_contract(*, registry_path: Path = DEFAULT_REGISTRY_PATH, output_path: Path = DEFAULT_OUTPUT_PATH) -> dict[str, Any]:
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

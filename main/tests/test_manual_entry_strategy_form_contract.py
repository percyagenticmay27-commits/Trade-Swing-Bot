import json
from pathlib import Path

from swing_trade_bot.manual_entry_strategy_form_contract import (
    build_manual_entry_strategy_form_contract,
    write_manual_entry_strategy_form_contract,
)


def _registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.4",
                "paper_trade_mode": True,
                "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR",
                "default_strategy_id": "TEST",
                "strategies": [
                    {
                        "strategy_id": "TEST",
                        "name": "Test",
                        "timeframe": "1D",
                        "direction": "LONG",
                        "session": "REGULAR_SESSION",
                        "rule_logic": "ALL",
                        "number_of_entries": 3,
                        "confirmation_bars": 2,
                        "enabled": True,
                        "rules": [{"left": "close", "operator": ">", "right": "ema", "period": 20}],
                        "regime_logic": "ALL",
                        "regime_filters": [{"left": "rsi", "operator": ">=", "right": 45, "period": 14}],
                        "normal_exit_logic": "ANY",
                        "normal_exit_rules": [{"left": "close", "operator": "<", "right": "ema", "period": 18}],
                        "conditional_exits": [],
                    }
                ],
                "assignments": [{"underlying_symbol": "NFLX", "strategy_id": "TEST", "assignment_mode": "DIRECT", "enabled": True}],
            }
        ),
        encoding="utf-8",
    )


def test_contract_exposes_manual_form_and_current_registry(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    payload = build_manual_entry_strategy_form_contract(registry_path=registry)
    assert payload["strategy_id"] == "SWING-001"
    assert payload["display_name"] == "Manual Strategy"
    assert payload["schema_version"] == "1.4"
    assert payload["current_registry"]["strategies"][0]["confirmation_bars"] == 2
    assert payload["current_registry"]["strategies"][0]["normal_exit_rules"][0]["period"] == 18


def test_number_of_entries_is_user_input_but_allocation_is_read_only(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    fields = {item["name"]: item for item in build_manual_entry_strategy_form_contract(registry_path=registry)["fields"]}
    assert fields["number_of_entries"]["type"] == "integer"
    assert fields["allocation_authority"]["type"] == "readonly"
    assert fields["allocation_authority"]["value"] == "SWING_PORTFOLIO_ALLOCATOR"
    assert "position_size" not in fields


def test_contract_exposes_frozen_strategy_lifecycle_fields(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    fields = {item["name"]: item for item in build_manual_entry_strategy_form_contract(registry_path=registry)["fields"]}
    assert fields["rules"]["parameter_columns"] == ["period", "factor", "smoothing", "price_source"]
    assert "WILDER" in fields["rules"]["smoothing_choices"]
    assert "OHLC_AVERAGE" in fields["rules"]["price_source_choices"]
    assert fields["confirmation_bars"]["minimum"] == 1
    assert fields["normal_exit_rules"]["type"] == "rule_list"
    assert fields["conditional_exit_pl_threshold"]["default"] == 0
    assert fields["conditional_exit_cooldown_bars"]["type"] == "integer"
    assert fields["conditional_exit_cooldown_unit"]["choices"] == ["TRADING_DAY", "BAR"]


def test_contract_documents_fields_with_help_and_examples(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    fields = {item["name"]: item for item in build_manual_entry_strategy_form_contract(registry_path=registry)["fields"]}
    for name in (
        "strategy_id", "name", "underlying_symbol", "assignment_mode", "timeframe", "session",
        "number_of_entries", "rules", "confirmation_bars", "regime_filters", "normal_exit_rules",
        "conditional_exit_enabled", "conditional_exit_pl_threshold", "conditional_exit_rules",
        "conditional_exit_cooldown_bars", "allocation_authority", "paper_trade_mode",
    ):
        assert fields[name]["help"]
        assert fields[name]["example"]
    assert "M_HMA50_DAILY" in fields["strategy_id"]["example"]
    assert "keltner_middle" in fields["rules"]["example"]


def test_contract_is_paper_only_and_host_uses_swing_intake(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    payload = build_manual_entry_strategy_form_contract(registry_path=registry)
    assert payload["paper_trade_mode"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["broker_execution_enabled"] is False
    assert payload["capital_movement_enabled"] is False
    assert payload["host_may_write_strategy_storage_directly"] is False
    assert payload["submission_contract"]["status"] == "AVAILABLE"
    assert payload["submission_contract"]["host_route"] == "/strategy/manual-entry"


def test_contract_write_is_atomic_shape(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    payload = build_manual_entry_strategy_form_contract(registry_path=registry)
    output = tmp_path / "form.json"
    assert write_manual_entry_strategy_form_contract(payload, output_path=output) == output
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["form_id"] == "SWING_MANUAL_TRADING_STRATEGY"
    assert not output.with_suffix(".json.tmp").exists()

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
                "schema_version": "1.2",
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
                        "enabled": True,
                        "rules": [
                            {"left": "close", "operator": ">", "right": "ema", "period": 20}
                        ],
                        "regime_logic": "ALL",
                        "regime_filters": [
                            {"left": "rsi", "operator": ">=", "right": 45, "period": 14}
                        ],
                    }
                ],
                "assignments": [
                    {"underlying_symbol": "NFLX", "strategy_id": "TEST", "enabled": True}
                ],
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
    assert payload["allocation_authority"] == "SWING_PORTFOLIO_ALLOCATOR"
    assert payload["current_registry"]["strategies"][0]["number_of_entries"] == 3
    assert payload["current_registry"]["strategies"][0]["regime_filters"][0]["left"] == "rsi"
    assert payload["current_registry"]["assignments"][0]["underlying_symbol"] == "NFLX"


def test_number_of_entries_is_user_input_but_allocation_is_read_only(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    payload = build_manual_entry_strategy_form_contract(registry_path=registry)
    fields = {item["name"]: item for item in payload["fields"]}

    assert fields["number_of_entries"]["type"] == "integer"
    assert fields["number_of_entries"]["minimum"] == 1
    assert fields["allocation_authority"]["type"] == "readonly"
    assert fields["allocation_authority"]["value"] == "SWING_PORTFOLIO_ALLOCATOR"
    assert "position_size" not in fields
    assert "allocation_percent" not in fields


def test_regime_filters_are_structured_not_comma_storage(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    payload = build_manual_entry_strategy_form_contract(registry_path=registry)
    fields = {item["name"]: item for item in payload["fields"]}

    assert fields["regime_filters"]["type"] == "rule_list"
    assert fields["regime_filters"]["storage"] == "STRUCTURED_LIST_NOT_COMMA_STRING"
    assert fields["regime_logic"]["choices"] == ["ALL", "ANY"]


def test_contract_is_paper_only_and_host_uses_swing_intake(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    payload = build_manual_entry_strategy_form_contract(registry_path=registry)

    assert payload["paper_trade_mode"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["broker_execution_enabled"] is False
    assert payload["order_placement_enabled"] is False
    assert payload["capital_movement_enabled"] is False
    assert payload["host_may_write_strategy_storage_directly"] is False
    submission = payload["submission_contract"]
    assert submission["status"] == "INTAKE_HANDLER_AVAILABLE"
    assert submission["handler_module"] == "swing_trade_bot.manual_entry_strategy_intake"
    assert submission["allocation_fields_user_writable"] is False
    assert submission["execution_vehicle_user_writable"] is False


def test_contract_write_is_atomic_shape(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    payload = build_manual_entry_strategy_form_contract(registry_path=registry)
    output = tmp_path / "form.json"

    assert write_manual_entry_strategy_form_contract(payload, output_path=output) == output
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["form_id"] == "SWING_MANUAL_ENTRY_STRATEGY"
    assert not output.with_suffix(".json.tmp").exists()

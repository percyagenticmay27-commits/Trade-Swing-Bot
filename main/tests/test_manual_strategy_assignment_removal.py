import json
from pathlib import Path

import pytest

from swing_trade_bot.manual_strategy_assignment_removal import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    HISTORICAL_EVIDENCE_DELETION_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_POSITION_CREATION_ENABLED,
    PAPER_TRADE_MODE,
    remove_manual_strategy_assignment,
)


def _strategy(strategy_id: str) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "name": strategy_id,
        "timeframe": "1D",
        "rule_logic": "ALL",
        "rules": [{"left": "close", "operator": ">", "right": "ema", "period": 14}],
        "number_of_entries": 1,
        "enabled": True,
        "direction": "LONG",
        "session": "08:30-14:30 CT",
        "confirmation_bars": 1,
        "regime_logic": "ALL",
        "regime_filters": [],
        "normal_exit_logic": "ANY",
        "normal_exit_rules": [],
        "conditional_exits": [],
        "paper_trade_mode": True,
    }


def _registry(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.4",
                "paper_trade_mode": True,
                "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR",
                "default_strategy_id": None,
                "strategies": [
                    _strategy("ACTIVE_DIRECT"),
                    _strategy("TRANSPORT_DIAGNOSTIC"),
                    _strategy("OTHER_SHADOW"),
                ],
                "assignments": [
                    {
                        "underlying_symbol": "NFLX",
                        "strategy_id": "ACTIVE_DIRECT",
                        "assignment_mode": "DIRECT",
                        "enabled": True,
                        "note": "keep direct",
                    },
                    {
                        "underlying_symbol": "NFLX",
                        "strategy_id": "TRANSPORT_DIAGNOSTIC",
                        "assignment_mode": "SHADOW",
                        "enabled": True,
                        "note": "transport test only",
                    },
                    {
                        "underlying_symbol": "NFLX",
                        "strategy_id": "OTHER_SHADOW",
                        "assignment_mode": "SHADOW",
                        "enabled": True,
                        "note": "keep research",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_exact_shadow_assignment_can_be_removed_without_touching_others(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    form = tmp_path / "form.json"
    report = tmp_path / "report.json"
    _registry(registry)

    result = remove_manual_strategy_assignment(
        underlying_symbol="NFLX",
        strategy_id="TRANSPORT_DIAGNOSTIC",
        assignment_mode="SHADOW",
        confirm=True,
        registry_path=registry,
        form_contract_path=form,
        assignment_report_path=report,
    )

    payload = json.loads(registry.read_text(encoding="utf-8"))
    keys = {
        (a["underlying_symbol"], a["strategy_id"], a["assignment_mode"])
        for a in payload["assignments"]
    }
    assert ("NFLX", "TRANSPORT_DIAGNOSTIC", "SHADOW") not in keys
    assert ("NFLX", "ACTIVE_DIRECT", "DIRECT") in keys
    assert ("NFLX", "OTHER_SHADOW", "SHADOW") in keys
    assert any(s["strategy_id"] == "TRANSPORT_DIAGNOSTIC" for s in payload["strategies"])
    assert result.strategy_definition_removed is False
    assert form.is_file()
    assert report.is_file()


def test_explicit_prune_removes_only_unreferenced_strategy_definition(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)

    result = remove_manual_strategy_assignment(
        underlying_symbol="NFLX",
        strategy_id="TRANSPORT_DIAGNOSTIC",
        assignment_mode="SHADOW",
        confirm=True,
        prune_unreferenced_strategy=True,
        registry_path=registry,
        form_contract_path=tmp_path / "form.json",
        assignment_report_path=tmp_path / "report.json",
    )
    payload = json.loads(registry.read_text(encoding="utf-8"))
    assert not any(s["strategy_id"] == "TRANSPORT_DIAGNOSTIC" for s in payload["strategies"])
    assert result.strategy_definition_removed is True


def test_removal_requires_explicit_confirmation_and_exact_identity(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    original = registry.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="explicit user confirmation"):
        remove_manual_strategy_assignment(
            underlying_symbol="NFLX",
            strategy_id="TRANSPORT_DIAGNOSTIC",
            assignment_mode="SHADOW",
            confirm=False,
            registry_path=registry,
        )
    assert registry.read_text(encoding="utf-8") == original

    with pytest.raises(ValueError, match="assignment not found"):
        remove_manual_strategy_assignment(
            underlying_symbol="NFLX",
            strategy_id="TRANSPORT_DIAGNOSTIC",
            assignment_mode="DIRECT",
            confirm=True,
            registry_path=registry,
        )
    assert registry.read_text(encoding="utf-8") == original


def test_removal_does_not_delete_history_or_expose_execution_authority(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry)
    history = tmp_path / "shadow_strategy_performance.json"
    history.write_text('{"rows":[{"strategy_id":"TRANSPORT_DIAGNOSTIC","net_pl":12.34}]}', encoding="utf-8")

    remove_manual_strategy_assignment(
        underlying_symbol="NFLX",
        strategy_id="TRANSPORT_DIAGNOSTIC",
        assignment_mode="SHADOW",
        confirm=True,
        registry_path=registry,
        form_contract_path=tmp_path / "form.json",
        assignment_report_path=tmp_path / "report.json",
    )
    assert "TRANSPORT_DIAGNOSTIC" in history.read_text(encoding="utf-8")
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert PAPER_POSITION_CREATION_ENABLED is False
    assert HISTORICAL_EVIDENCE_DELETION_ENABLED is False

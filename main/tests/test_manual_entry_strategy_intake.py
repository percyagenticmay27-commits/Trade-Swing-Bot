import json
from pathlib import Path

import pytest

from swing_trade_bot.manual_entry_strategy_intake import (
    apply_manual_entry_strategy_submission,
)
from swing_trade_bot.manual_entry_strategy_registry import (
    load_manual_entry_strategy_registry,
)


def _registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.4",
                "paper_trade_mode": True,
                "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR",
                "default_strategy_id": None,
                "strategies": [],
                "assignments": [],
            }
        ),
        encoding="utf-8",
    )


def _submission(strategy_id: str = "NFLX_DAILY_KELTNER", symbol: str = "NFLX", mode: str = "DIRECT") -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "name": strategy_id.replace("_", " ").title(),
        "underlying_symbol": symbol,
        "assignment_mode": mode,
        "enabled": True,
        "direction": "LONG",
        "timeframe": "1D",
        "session": "REGULAR_SESSION",
        "number_of_entries": 2,
        "rule_logic": "ALL",
        "rules": [
            {"left": "close", "operator": ">", "right": "ema", "period": 14},
            {"left": "rsi", "operator": "between", "right": [45, 65], "period": 14},
        ],
        "confirmation": {"consecutive_bars": 2},
        "regime_logic": "ALL",
        "regime_filters": [
            {"left": "market_filter", "operator": "==", "right": "satisfied"}
        ],
        "exit_policy_id": "TIERED_TRAILING",
        "reentry_cooldown": {"bars": 1},
        "paper_trade_mode": True,
    }


def test_intake_creates_strategy_and_underlying_assignment(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)

    result = apply_manual_entry_strategy_submission(
        _submission(), registry_path=registry_path, form_contract_path=form_path
    )
    registry = load_manual_entry_strategy_registry(registry_path)

    assert result.status == "SAVED"
    assert result.created_strategy is True
    assert result.created_assignment is True
    strategy = registry.resolve("NFLX")
    assert strategy is not None
    assert strategy.strategy_id == "NFLX_DAILY_KELTNER"
    assert strategy.number_of_entries == 2
    assert strategy.confirmation == {"consecutive_bars": 2}
    assert strategy.regime_filters[0].left == "market_filter"
    assert strategy.exit_policy_id == "TIERED_TRAILING"
    assert strategy.reentry_cooldown == {"bars": 1}


def test_intake_normalizes_user_facing_indicator_case(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)
    submission = _submission()
    submission["rules"] = [
        {"left": "Close", "operator": ">", "right": "EMA", "period": 14},
        {
            "left": "Close",
            "operator": ">",
            "right": "KELTNER_MIDDLE",
            "period": 14,
            "factor": 1,
            "smoothing": "WILDER",
            "price_source": "OHLC_AVERAGE",
        },
    ]
    submission["regime_filters"] = [
        {"left": "CHOP", "operator": "<", "right": 60, "period": 14}
    ]

    apply_manual_entry_strategy_submission(
        submission, registry_path=registry_path, form_contract_path=form_path
    )
    strategy = load_manual_entry_strategy_registry(registry_path).resolve("NFLX")

    assert strategy is not None
    assert strategy.rules[0].left == "close"
    assert strategy.rules[0].right == "ema"
    assert strategy.rules[1].right == "keltner_middle"
    assert strategy.regime_filters[0].left == "chop"


def test_intake_updates_existing_strategy_and_assignment_without_duplicates(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)
    submission = _submission()
    apply_manual_entry_strategy_submission(
        submission, registry_path=registry_path, form_contract_path=form_path
    )
    submission["number_of_entries"] = 3
    submission["name"] = "NFLX Revised"
    second = apply_manual_entry_strategy_submission(
        submission, registry_path=registry_path, form_contract_path=form_path
    )
    registry = load_manual_entry_strategy_registry(registry_path)

    assert second.created_strategy is False
    assert second.created_assignment is False
    assert len(registry.strategies) == 1
    assert len(registry.assignments) == 1
    assert registry.strategies[0].number_of_entries == 3
    assert registry.strategies[0].name == "NFLX Revised"
    assert registry.assignments[0].assignment_mode == "DIRECT"


def test_new_direct_demotes_previous_direct_to_shadow_and_preserves_definition(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)
    first = _submission("STRATEGY_A")
    first["assignment_enabled"] = False
    first["assignment_note"] = "preserve me"
    apply_manual_entry_strategy_submission(first, registry_path=registry_path, form_contract_path=form_path)
    apply_manual_entry_strategy_submission(_submission("STRATEGY_C"), registry_path=registry_path, form_contract_path=form_path)

    registry = load_manual_entry_strategy_registry(registry_path)
    direct = [a for a in registry.assignments if a.underlying_symbol == "NFLX" and a.assignment_mode == "DIRECT"]
    shadows = [a for a in registry.assignments if a.underlying_symbol == "NFLX" and a.assignment_mode == "SHADOW"]

    assert [a.strategy_id for a in direct] == ["STRATEGY_C"]
    assert [a.strategy_id for a in shadows] == ["STRATEGY_A"]
    assert shadows[0].enabled is False
    assert shadows[0].note == "preserve me"
    assert {s.strategy_id for s in registry.strategies} == {"STRATEGY_A", "STRATEGY_C"}


def test_new_direct_preserves_unrelated_shadows_and_other_symbols(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)
    for submission in (
        _submission("STRATEGY_A"),
        _submission("STRATEGY_B", mode="SHADOW"),
        _submission("GOOG_DIRECT", symbol="GOOG"),
        _submission("STRATEGY_C"),
    ):
        apply_manual_entry_strategy_submission(submission, registry_path=registry_path, form_contract_path=form_path)

    registry = load_manual_entry_strategy_registry(registry_path)
    nflx_shadows = {a.strategy_id for a in registry.assignments if a.underlying_symbol == "NFLX" and a.assignment_mode == "SHADOW"}
    goog_direct = [a for a in registry.assignments if a.underlying_symbol == "GOOG" and a.assignment_mode == "DIRECT"]
    assert nflx_shadows == {"STRATEGY_A", "STRATEGY_B"}
    assert [a.strategy_id for a in goog_direct] == ["GOOG_DIRECT"]


def test_displaced_direct_reuses_existing_equivalent_shadow_without_duplicate(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)
    apply_manual_entry_strategy_submission(_submission("STRATEGY_A"), registry_path=registry_path, form_contract_path=form_path)
    registry = load_manual_entry_strategy_registry(registry_path)
    # Construct a legacy-but-valid registry state containing an equivalent shadow.
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["assignments"].append({
        "underlying_symbol": "NFLX",
        "strategy_id": "STRATEGY_A",
        "assignment_mode": "SHADOW",
        "enabled": True,
        "note": "older shadow",
    })
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    apply_manual_entry_strategy_submission(_submission("STRATEGY_C"), registry_path=registry_path, form_contract_path=form_path)
    registry = load_manual_entry_strategy_registry(registry_path)
    equivalent = [a for a in registry.assignments if a.underlying_symbol == "NFLX" and a.strategy_id == "STRATEGY_A" and a.assignment_mode == "SHADOW"]
    assert len(equivalent) == 1


def test_resubmitting_current_direct_is_idempotent_and_creates_no_shadow(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)
    submission = _submission("STRATEGY_A")
    apply_manual_entry_strategy_submission(submission, registry_path=registry_path, form_contract_path=form_path)
    apply_manual_entry_strategy_submission(submission, registry_path=registry_path, form_contract_path=form_path)
    registry = load_manual_entry_strategy_registry(registry_path)

    assert [(a.strategy_id, a.assignment_mode) for a in registry.assignments if a.underlying_symbol == "NFLX"] == [("STRATEGY_A", "DIRECT")]


def test_intake_regenerates_host_readable_contract(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)
    apply_manual_entry_strategy_submission(
        _submission(), registry_path=registry_path, form_contract_path=form_path
    )
    contract = json.loads(form_path.read_text(encoding="utf-8"))

    assert contract["submission_contract"]["status"] == "AVAILABLE"
    assert contract["submission_contract"]["host_route"] == "/strategy/manual-entry"
    assert contract["submission_contract"]["host_transport"] == "LOCAL_SWING_CLI_STDIN_JSON"
    assert contract["current_registry"]["assignments"][0]["underlying_symbol"] == "NFLX"
    assert contract["current_registry"]["strategies"][0]["number_of_entries"] == 2


def test_intake_rejects_user_allocation_or_execution_authority(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)

    for field, value in (("allocation_amount", 500), ("position_size", 250), ("execution_symbol", "NFLU")):
        submission = _submission()
        submission[field] = value
        with pytest.raises(ValueError, match="Swing-owned fields"):
            apply_manual_entry_strategy_submission(
                submission, registry_path=registry_path, form_contract_path=form_path
            )


def test_paper_trade_mode_false_is_rejected(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)
    submission = _submission()
    submission["paper_trade_mode"] = False
    with pytest.raises(ValueError, match="paper_trade_mode=True"):
        apply_manual_entry_strategy_submission(submission, registry_path=registry_path, form_contract_path=form_path)


def test_invalid_submission_does_not_modify_registry(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _registry(registry_path)
    before = registry_path.read_text(encoding="utf-8")
    submission = _submission()
    submission["number_of_entries"] = 0

    with pytest.raises(ValueError):
        apply_manual_entry_strategy_submission(
            submission, registry_path=registry_path, form_contract_path=form_path
        )

    assert registry_path.read_text(encoding="utf-8") == before


def test_intake_is_paper_only_and_has_no_execution_side_effects() -> None:
    import swing_trade_bot.manual_entry_strategy_intake as module

    assert module.PAPER_TRADE_MODE is True
    assert module.LIVE_TRADING_ENABLED is False
    assert module.BROKER_EXECUTION_ENABLED is False
    assert module.ORDER_PLACEMENT_ENABLED is False
    assert module.CAPITAL_MOVEMENT_ENABLED is False
    assert module.PAPER_POSITION_CREATION_ENABLED is False

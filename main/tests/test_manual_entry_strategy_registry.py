import json
from pathlib import Path

import pytest

from swing_trade_bot.manual_entry_strategy_registry import (
    EntryRule,
    ManualEntryStrategy,
    ManualEntryStrategyRegistry,
    UnderlyingEntryAssignment,
    load_manual_entry_strategy_registry,
    write_manual_entry_strategy_registry,
)


def _strategy(strategy_id: str = "TEST_DAILY", *, number_of_entries: int = 1) -> ManualEntryStrategy:
    return ManualEntryStrategy(
        strategy_id=strategy_id,
        name="Test Daily",
        timeframe="1D",
        rule_logic="ALL",
        rules=(
            EntryRule("close", ">", "ema", period=20),
            EntryRule("rsi", "between", [45.0, 65.0], period=14),
        ),
        number_of_entries=number_of_entries,
    )


def test_explicit_underlying_assignment_resolves_strategy() -> None:
    strategy = _strategy()
    registry = ManualEntryStrategyRegistry(
        strategies=(strategy,),
        assignments=(UnderlyingEntryAssignment("NFLX", "TEST_DAILY"),),
    )

    assert registry.resolve("nflx") == strategy


def test_assignment_is_to_underlying_not_leveraged_vehicle() -> None:
    strategy = _strategy()
    registry = ManualEntryStrategyRegistry(
        strategies=(strategy,),
        assignments=(UnderlyingEntryAssignment("NFLX", "TEST_DAILY"),),
    )

    assert registry.resolve("NFLX") == strategy
    assert registry.resolve("NFLU") is None


def test_default_strategy_is_used_when_no_explicit_assignment() -> None:
    strategy = _strategy()
    registry = ManualEntryStrategyRegistry(
        strategies=(strategy,),
        assignments=(),
        default_strategy_id="TEST_DAILY",
    )

    assert registry.resolve("NVDA") == strategy


def test_explicit_assignment_takes_precedence_over_default() -> None:
    default = _strategy("DEFAULT")
    alternate = _strategy("ALT", number_of_entries=2)
    registry = ManualEntryStrategyRegistry(
        strategies=(default, alternate),
        assignments=(UnderlyingEntryAssignment("AMZN", "ALT"),),
        default_strategy_id="DEFAULT",
    )

    assert registry.resolve("AMZN") == alternate
    assert registry.resolve("AMZN").number_of_entries == 2  # type: ignore[union-attr]
    assert registry.resolve("NFLX") == default


def test_number_of_entries_defaults_to_one_and_accepts_staged_counts() -> None:
    assert _strategy().number_of_entries == 1
    assert _strategy(number_of_entries=2).number_of_entries == 2
    assert _strategy(number_of_entries=3).number_of_entries == 3


def test_invalid_number_of_entries_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        _strategy(number_of_entries=0)


def test_duplicate_underlying_assignment_is_rejected() -> None:
    strategy = _strategy()
    with pytest.raises(ValueError, match="only one manual entry strategy"):
        ManualEntryStrategyRegistry(
            strategies=(strategy,),
            assignments=(
                UnderlyingEntryAssignment("NFLX", "TEST_DAILY"),
                UnderlyingEntryAssignment("NFLX", "TEST_DAILY"),
            ),
        )


def test_unknown_strategy_assignment_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown strategy_id"):
        ManualEntryStrategyRegistry(
            strategies=(_strategy(),),
            assignments=(UnderlyingEntryAssignment("NFLX", "MISSING"),),
        )


def test_disabled_assignment_does_not_override_default() -> None:
    default = _strategy("DEFAULT")
    alternate = _strategy("ALT")
    registry = ManualEntryStrategyRegistry(
        strategies=(default, alternate),
        assignments=(UnderlyingEntryAssignment("NFLX", "ALT", enabled=False),),
        default_strategy_id="DEFAULT",
    )

    assert registry.resolve("NFLX") == default


def test_load_and_atomic_write_round_trip(tmp_path: Path) -> None:
    registry = ManualEntryStrategyRegistry(
        strategies=(_strategy(number_of_entries=3),),
        assignments=(UnderlyingEntryAssignment("NFLX", "TEST_DAILY", note="manual test"),),
        default_strategy_id="TEST_DAILY",
    )
    path = tmp_path / "manual_entry_strategies.json"

    write_manual_entry_strategy_registry(path, registry)
    loaded = load_manual_entry_strategy_registry(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert loaded == registry
    assert payload["paper_trade_mode"] is True
    assert payload["schema_version"] == "1.2"
    assert payload["allocation_authority"] == "SWING_PORTFOLIO_ALLOCATOR"
    assert payload["strategies"][0]["number_of_entries"] == 3


def test_registry_is_configuration_only_and_paper_only() -> None:
    source = Path(
        "src/swing_trade_bot/manual_entry_strategy_registry.py"
    ).read_text(encoding="utf-8").lower()

    assert "place_order(" not in source
    assert "paper_positions" not in source
    assert "broker" in source  # documentation explicitly states broker orders are not exposed
    with pytest.raises(ValueError, match="paper_trade_mode=True"):
        ManualEntryStrategyRegistry(
            strategies=(_strategy(),),
            assignments=(),
            paper_trade_mode=False,
        )

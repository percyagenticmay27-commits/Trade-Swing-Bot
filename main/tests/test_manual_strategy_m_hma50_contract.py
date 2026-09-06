import json
from pathlib import Path

from swing_trade_bot.manual_entry_strategy_intake import apply_manual_entry_strategy_submission
from swing_trade_bot.manual_entry_strategy_registry import load_manual_entry_strategy_registry


def _empty_registry(path: Path) -> None:
    path.write_text(json.dumps({
        "schema_version": "1.4",
        "paper_trade_mode": True,
        "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR",
        "default_strategy_id": None,
        "strategies": [],
        "assignments": [],
    }), encoding="utf-8")


def test_nflx_m_hma50_daily_is_preserved_without_approximation(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    form_path = tmp_path / "form.json"
    _empty_registry(registry_path)

    submission = {
        "strategy_id": "M_HMA50_DAILY",
        "name": "M-HMA50 Daily",
        "underlying_symbol": "NFLX",
        "assignment_mode": "DIRECT",
        "direction": "LONG",
        "timeframe": "1D",
        "session": "08:30-14:30 CT",
        "number_of_entries": 1,
        "rule_logic": "ALL",
        "rules": [
            {
                "left": "close", "operator": ">", "right": "keltner_middle",
                "period": 14, "factor": 1, "smoothing": "WILDER", "price_source": "OHLC_AVERAGE",
            },
            {"left": "close", "operator": ">", "right": "ema", "period": 14},
        ],
        "confirmation_bars": 2,
        "regime_logic": "ALL",
        "regime_filters": [{"left": "chop", "operator": "<", "right": 60.0, "period": 14}],
        "normal_exit_logic": "ANY",
        "normal_exit_rules": [
            {"left": "close", "operator": "<", "right": "ema", "period": 18},
            {
                "left": "close", "operator": "<", "right": "keltner_middle",
                "period": 14, "factor": 1, "smoothing": "WILDER", "price_source": "OHLC_AVERAGE",
            },
        ],
        "conditional_exits": [
            {
                "condition": {"left": "position_pl", "operator": ">", "right": 0.0},
                "rule_logic": "ANY",
                "rules": [{"left": "close", "operator": "<", "right": "hma", "period": 50}],
                "action": "SELL",
                "cooldown_bars": 2,
                "cooldown_unit": "TRADING_DAY",
                "reset_entry_confirmation": True,
            }
        ],
        "paper_trade_mode": True,
    }

    apply_manual_entry_strategy_submission(submission, registry_path=registry_path, form_contract_path=form_path)
    registry = load_manual_entry_strategy_registry(registry_path)
    strategy = registry.resolve("NFLX")
    assert strategy is not None
    assert strategy.strategy_id == "M_HMA50_DAILY"
    assert strategy.session == "08:30-14:30 CT"
    assert strategy.confirmation_bars == 2

    keltner_entry = strategy.rules[0]
    assert keltner_entry.right == "keltner_middle"
    assert keltner_entry.period == 14
    assert keltner_entry.factor == 1
    assert keltner_entry.smoothing == "WILDER"
    assert keltner_entry.price_source == "OHLC_AVERAGE"

    assert strategy.regime_filters[0].left == "chop"
    assert strategy.regime_filters[0].period == 14
    assert strategy.regime_filters[0].right == 60.0
    assert strategy.normal_exit_logic == "ANY"
    assert strategy.normal_exit_rules[0].right == "ema"
    assert strategy.normal_exit_rules[0].period == 18
    assert strategy.normal_exit_rules[1].right == "keltner_middle"

    conditional = strategy.conditional_exits[0]
    assert conditional.condition.left == "position_pl"
    assert conditional.condition.operator == ">"
    assert conditional.condition.right == 0.0
    assert conditional.rules[0].right == "hma"
    assert conditional.rules[0].period == 50
    assert conditional.cooldown_bars == 2
    assert conditional.cooldown_unit == "TRADING_DAY"
    assert conditional.reset_entry_confirmation is True

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.4"
    assert payload["assignments"][0]["assignment_mode"] == "DIRECT"
    assert payload["allocation_authority"] == "SWING_PORTFOLIO_ALLOCATOR"

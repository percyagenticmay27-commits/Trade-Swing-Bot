from pathlib import Path

import swing_trade_bot.frozen_primary_operational_cycle as cycle


def test_operational_cycle_runs_governed_sequence_in_order(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(cycle, "refresh_intraday_market_data", lambda: calls.append("intraday") or {"symbols": []})
    monkeypatch.setattr(cycle, "synchronize_frozen_primary_authority", lambda: calls.append("authority") or {"rows": []})
    monkeypatch.setattr(cycle, "refresh_frozen_primary_reference_quantities", lambda: calls.append("reference") or {"rows": []})
    monkeypatch.setattr(cycle, "run_frozen_primary_signal_execution", lambda: calls.append("execution") or {"rows": [{"executed_events": [{"side": "SELL"}]}]})
    monkeypatch.setattr(
        cycle,
        "refresh_frozen_primary_post_execution_evidence",
        lambda repository_root: calls.append("post") or {"position_count": 0},
    )

    captured = {}
    def evidence(*, primary_positions_path):
        calls.append("evidence")
        captured["path"] = primary_positions_path
        return {"rows": []}
    monkeypatch.setattr(cycle, "build_and_write_frozen_strategy_evidence", evidence)

    result = cycle.run_frozen_primary_operational_cycle(repository_root=tmp_path)

    assert calls == ["intraday", "authority", "reference", "execution", "post", "reference", "evidence"]
    assert captured["path"] == cycle.DEFAULT_REFERENCE_PATH
    assert result["executed_event_count"] == 1
    assert result["sequence"] == [
        "INTRADAY_REFRESH",
        "DIRECT_AUTHORITY_SYNC",
        "REFERENCE_QUANTITY_BEFORE_EXECUTION",
        "DIRECT_PRIMARY_SIGNAL_EXECUTION",
        "POST_EXECUTION_PAPER_EVIDENCE",
        "REFERENCE_QUANTITY_AFTER_EXECUTION",
        "PRIMARY_SHADOW_RESEARCH_EVIDENCE",
    ]


def test_operational_cycle_safety_flags_are_locked(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "refresh_intraday_market_data", lambda: {})
    monkeypatch.setattr(cycle, "synchronize_frozen_primary_authority", lambda: {})
    monkeypatch.setattr(cycle, "refresh_frozen_primary_reference_quantities", lambda: {})
    monkeypatch.setattr(cycle, "run_frozen_primary_signal_execution", lambda: {"rows": []})
    monkeypatch.setattr(cycle, "refresh_frozen_primary_post_execution_evidence", lambda repository_root: {})
    monkeypatch.setattr(cycle, "build_and_write_frozen_strategy_evidence", lambda **kwargs: {})

    result = cycle.run_frozen_primary_operational_cycle(repository_root=tmp_path)

    assert result["paper_trade_mode"] is True
    assert result["live_trading_enabled"] is False
    assert result["broker_execution_enabled"] is False
    assert result["order_placement_enabled"] is False
    assert result["capital_movement_enabled"] is False
    assert result["shadow_execution_enabled"] is False


def test_default_shadow_quantity_authority_is_persistent_reference_file():
    from swing_trade_bot.frozen_strategy_operational_workflow import DEFAULT_PRIMARY_POSITIONS_PATH

    assert DEFAULT_PRIMARY_POSITIONS_PATH == Path("results/frozen_primary_reference_positions.csv")

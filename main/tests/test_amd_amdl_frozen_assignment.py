import json
from pathlib import Path

from swing_trade_bot.frozen_strategy_assignment_registry import resolve_frozen_stack


CONFIG_PATH = Path("configs/frozen_strategy_assignments.json")


def test_amd_amdl_frozen_assignment_stack() -> None:
    stack = resolve_frozen_stack("AMDL", CONFIG_PATH)
    assert stack is not None
    assert stack.research_status == "AMD_SIGNAL_MAPPED_AMDL_PAPER_VALIDATION"
    assert stack.primary.strategy_id == "AMDL_AMD_AI_C2_QUALITY_1H_PRIMARY"
    assert [item.strategy_id for item in stack.shadows] == [
        "AMDL_AMD_AI_C2_PROFIT_1H_SHADOW_1",
        "AMDL_AMD_ZERO_LAG_BALANCE_1H_SHADOW_2",
        "AMDL_AMD_AI_C1_DAILY_SHADOW_3",
        "AMDL_AMD_ZERO_LAG_NATIVE_1H_SHADOW_4",
    ]


def test_amd_amdl_mapping_is_paper_only_and_uses_underlying_signals() -> None:
    stack = resolve_frozen_stack("AMDL", CONFIG_PATH)
    assert stack is not None
    specs = (stack.primary, *stack.shadows)

    assert len(stack.shadows) == 4
    assert all(spec.signal_symbol == "AMD" for spec in specs)
    assert all(spec.vehicle_symbol == "AMDL" for spec in specs)
    assert all(spec.paper_trade_mode is True for spec in specs)
    assert all(spec.catastrophic_stop_percent == 20.0 for spec in specs)


def test_amd_primary_checkpoint_and_parameters_are_frozen() -> None:
    stack = resolve_frozen_stack("AMDL", CONFIG_PATH)
    assert stack is not None
    spec = stack.primary

    assert spec.engine_id == "C2_RECON"
    assert spec.timeframe == "1H"
    assert spec.parameters == {
        "mode": "K_K_CROSS",
        "hma_length": 0,
        "chop_max": 45.0,
        "adx_min": 0.0,
        "rsi_min": 50.0,
    }


def test_amd_historical_checkpoints_share_same_validation_period() -> None:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    rows = {
        row["strategy_id"]: row
        for row in payload["strategies"]
        if row["strategy_id"].startswith("AMDL_AMD_")
    }
    expected = {
        "AMDL_AMD_AI_C2_QUALITY_1H_PRIMARY": (170, 57.65, 52.72, 2.08, 6.43),
        "AMDL_AMD_AI_C2_PROFIT_1H_SHADOW_1": (330, 53.64, 97.06, 1.76, 13.13),
        "AMDL_AMD_ZERO_LAG_BALANCE_1H_SHADOW_2": (33, 66.67, 193.19, 3.576, 22.64),
        "AMDL_AMD_AI_C1_DAILY_SHADOW_3": (70, 68.57, 93.95, 2.32, 13.01),
        "AMDL_AMD_ZERO_LAG_NATIVE_1H_SHADOW_4": (48, 50.00, 194.88, 2.709, 19.57),
    }

    assert set(rows) == set(expected)
    for strategy_id, metrics in expected.items():
        checkpoint = rows[strategy_id]["frozen_checkpoint"]
        assert checkpoint["source_symbol"] == "AMD"
        assert checkpoint["deployment_vehicle"] == "AMDL"
        assert checkpoint["backtest_period"] == "2023-01-01_to_2026-08-28"
        assert "HISTORICAL_REFERENCE_ONLY" in checkpoint["checkpoint_scope"]
        actual = (
            checkpoint["trade_count"],
            checkpoint["win_rate_percent"],
            checkpoint["net_pl_dollars"],
            checkpoint["profit_factor"],
            checkpoint["max_drawdown_dollars"],
        )
        assert actual == metrics

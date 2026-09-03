from swing_trade_bot.frozen_strategy_assignment_registry import load_frozen_strategy_assignment_registry


def test_amd_amdl_frozen_assignment_stack():
    registry = load_frozen_strategy_assignment_registry()
    symbol = registry.symbols["AMDL"]

    assert symbol.primary_strategy_id == "AMDL_AMD_AI_C2_QUALITY_1H_PRIMARY"
    assert symbol.shadow_strategy_ids == (
        "AMDL_AMD_AI_C2_PROFIT_1H_SHADOW_1",
        "AMDL_AMD_ZERO_LAG_BALANCE_1H_SHADOW_2",
        "AMDL_AMD_AI_C1_DAILY_SHADOW_3",
        "AMDL_AMD_ZERO_LAG_NATIVE_1H_SHADOW_4",
    )


def test_amd_amdl_mapping_is_paper_only_and_uses_underlying_signals():
    registry = load_frozen_strategy_assignment_registry()
    ids = (
        "AMDL_AMD_AI_C2_QUALITY_1H_PRIMARY",
        "AMDL_AMD_AI_C2_PROFIT_1H_SHADOW_1",
        "AMDL_AMD_ZERO_LAG_BALANCE_1H_SHADOW_2",
        "AMDL_AMD_AI_C1_DAILY_SHADOW_3",
        "AMDL_AMD_ZERO_LAG_NATIVE_1H_SHADOW_4",
    )

    for strategy_id in ids:
        spec = registry.strategies[strategy_id]
        assert spec.signal_symbol == "AMD"
        assert spec.vehicle_symbol == "AMDL"
        assert spec.paper_trade_mode is True
        assert spec.catastrophic_stop_percent == 20.0


def test_amd_historical_checkpoints_share_same_validation_period():
    registry = load_frozen_strategy_assignment_registry()
    ids = (
        "AMDL_AMD_AI_C2_QUALITY_1H_PRIMARY",
        "AMDL_AMD_AI_C2_PROFIT_1H_SHADOW_1",
        "AMDL_AMD_ZERO_LAG_BALANCE_1H_SHADOW_2",
        "AMDL_AMD_AI_C1_DAILY_SHADOW_3",
        "AMDL_AMD_ZERO_LAG_NATIVE_1H_SHADOW_4",
    )

    checkpoints = [registry.strategies[x].frozen_checkpoint for x in ids]
    assert {x["backtest_period"] for x in checkpoints} == {"2023-01-01_to_2026-08-28"}
    assert all(x["source_symbol"] == "AMD" for x in checkpoints)
    assert all(x["deployment_vehicle"] == "AMDL" for x in checkpoints)


def test_amd_primary_checkpoint_and_parameters_are_frozen():
    registry = load_frozen_strategy_assignment_registry()
    spec = registry.strategies["AMDL_AMD_AI_C2_QUALITY_1H_PRIMARY"]

    assert spec.engine_id == "C2_RECON"
    assert spec.timeframe == "1H"
    assert spec.parameters == {
        "mode": "K_K_CROSS",
        "hma_length": 0,
        "chop_max": 45.0,
        "adx_min": 0.0,
        "rsi_min": 50.0,
    }
    assert spec.frozen_checkpoint["trade_count"] == 170
    assert spec.frozen_checkpoint["win_rate_percent"] == 57.65
    assert spec.frozen_checkpoint["net_pl_dollars"] == 52.72
    assert spec.frozen_checkpoint["profit_factor"] == 2.08
    assert spec.frozen_checkpoint["max_drawdown_dollars"] == 6.43

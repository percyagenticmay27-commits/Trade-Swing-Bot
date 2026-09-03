from datetime import date, timedelta

from swing_trade_bot.frozen_ai_signal_engines import (
    SUPPORTED_ENGINES,
    evaluate_frozen_signal,
    frozen_engine_execution_timing,
)
from swing_trade_bot.position_state import MarketBar


def _bars(count: int = 260) -> list[MarketBar]:
    start = date(2025, 1, 2)
    rows: list[MarketBar] = []
    price = 100.0
    for index in range(count):
        drift = 0.35 if (index // 12) % 2 == 0 else -0.20
        price = max(10.0, price + drift + (0.15 if index % 5 == 0 else 0.0))
        rows.append(MarketBar(
            date=start + timedelta(days=index),
            open=price - 0.10,
            high=price + 0.60,
            low=price - 0.60,
            close=price,
            volume=1000.0 + index,
        ))
    return rows


def test_c1_c2_are_supported_and_use_next_chart_bar_open() -> None:
    assert "C1_RECON" in SUPPORTED_ENGINES
    assert "C2_RECON" in SUPPORTED_ENGINES
    assert frozen_engine_execution_timing("C1_RECON") == "CONFIRMED_SIGNAL_NEXT_CHART_BAR_OPEN"
    assert frozen_engine_execution_timing("C2_RECON") == "CONFIRMED_SIGNAL_NEXT_CHART_BAR_OPEN"


def test_c1_reconstruction_accepts_pltr_frozen_filters() -> None:
    decision = evaluate_frozen_signal(
        "C1_RECON",
        {"hma_length": 200, "chop_max": 0.0, "adx_min": 15.0, "rsi_min": 0.0},
        _bars(),
    )
    assert decision.engine_id == "C1_RECON"
    assert isinstance(decision.entry_signal, bool)
    assert isinstance(decision.exit_signal, bool)
    assert decision.diagnostics["ai_reconstructed"] is True


def test_c2_reconstruction_accepts_pltr_frozen_k_k_mode() -> None:
    decision = evaluate_frozen_signal(
        "C2_RECON",
        {"mode": "K_K_CROSS", "hma_length": 0, "chop_max": 0.0, "adx_min": 15.0, "rsi_min": 0.0},
        _bars(120),
    )
    assert decision.engine_id == "C2_RECON"
    assert isinstance(decision.entry_signal, bool)
    assert isinstance(decision.exit_signal, bool)
    assert decision.diagnostics["ai_reconstructed"] is True
    assert decision.diagnostics["mode"] == "K_K_CROSS"


def test_reconstructed_engines_fail_closed_without_history() -> None:
    c1 = evaluate_frozen_signal("C1_RECON", {}, _bars(10))
    c2 = evaluate_frozen_signal("C2_RECON", {"mode": "K_K_CROSS"}, _bars(10))
    assert c1.entry_signal is False and c1.exit_signal is False
    assert c2.entry_signal is False and c2.exit_signal is False
    assert c1.diagnostics["ready"] is False
    assert c2.diagnostics["ready"] is False

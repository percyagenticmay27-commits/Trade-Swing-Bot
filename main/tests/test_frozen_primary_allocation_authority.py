import json
from pathlib import Path

from swing_trade_bot.frozen_primary_allocation_authority import (
    resolve_frozen_primary_allocation_authority,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _portfolio(path: Path, rows: list[dict]) -> None:
    _write(path, {
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "allocations": rows,
    })


def _strategy_allocation(path: Path, amount: float = 4500.0) -> None:
    _write(path, {
        "payload": {
            "strategy_kpis": [{
                "strategy_id": "SWING-001",
                "allocated_capital": amount,
            }]
        }
    })


def test_underlying_allocation_maps_to_leveraged_vehicle_notional(tmp_path):
    portfolio = tmp_path / "portfolio_allocations.json"
    strategy = tmp_path / "strategy_allocations.json"
    _portfolio(portfolio, [{"symbol": "NFLX", "allocation_percent": 15.0}])
    _strategy_allocation(strategy, 4500.0)

    result = resolve_frozen_primary_allocation_authority(
        signal_symbol="NFLX",
        vehicle_symbol="NFLU",
        portfolio_allocation_path=portfolio,
        strategy_allocation_path=strategy,
    )

    assert result is not None
    assert result.allocation_symbol == "NFLX"
    assert result.allocation_percent == 15.0
    assert result.strategy_allocated_capital == 4500.0
    assert result.authorized_notional == 675.0
    assert result.paper_trade_mode is True
    assert result.capital_movement_enabled is False


def test_signal_symbol_wins_when_signal_and_vehicle_rows_both_exist(tmp_path):
    portfolio = tmp_path / "portfolio_allocations.json"
    strategy = tmp_path / "strategy_allocations.json"
    _portfolio(portfolio, [
        {"symbol": "NFLX", "allocation_percent": 20.0},
        {"symbol": "NFLU", "allocation_percent": 5.0},
    ])
    _strategy_allocation(strategy)

    result = resolve_frozen_primary_allocation_authority(
        signal_symbol="NFLX",
        vehicle_symbol="NFLU",
        portfolio_allocation_path=portfolio,
        strategy_allocation_path=strategy,
    )

    assert result is not None
    assert result.allocation_symbol == "NFLX"
    assert result.authorized_notional == 900.0


def test_same_symbol_allocation_is_supported(tmp_path):
    portfolio = tmp_path / "portfolio_allocations.json"
    strategy = tmp_path / "strategy_allocations.json"
    _portfolio(portfolio, [{"symbol": "SOXL", "allocation_percent": 25.0}])
    _strategy_allocation(strategy)

    result = resolve_frozen_primary_allocation_authority(
        signal_symbol="SOXL",
        vehicle_symbol="SOXL",
        portfolio_allocation_path=portfolio,
        strategy_allocation_path=strategy,
    )

    assert result is not None
    assert result.authorized_notional == 1125.0


def test_missing_security_allocation_fails_closed_without_loading_strategy_capital(tmp_path):
    portfolio = tmp_path / "portfolio_allocations.json"
    _portfolio(portfolio, [{"symbol": "QQQ", "allocation_percent": 15.0}])

    result = resolve_frozen_primary_allocation_authority(
        signal_symbol="NFLX",
        vehicle_symbol="NFLU",
        portfolio_allocation_path=portfolio,
        strategy_allocation_path=tmp_path / "does_not_exist.json",
    )

    assert result is None


def test_zero_security_allocation_fails_closed(tmp_path):
    portfolio = tmp_path / "portfolio_allocations.json"
    _portfolio(portfolio, [{"symbol": "NFLX", "allocation_percent": 0.0}])

    result = resolve_frozen_primary_allocation_authority(
        signal_symbol="NFLX",
        vehicle_symbol="NFLU",
        portfolio_allocation_path=portfolio,
        strategy_allocation_path=tmp_path / "does_not_exist.json",
    )

    assert result is None


def test_non_paper_portfolio_artifact_is_rejected(tmp_path):
    portfolio = tmp_path / "portfolio_allocations.json"
    _write(portfolio, {
        "paper_trade_mode": False,
        "capital_movement_enabled": False,
        "allocations": [{"symbol": "NFLX", "allocation_percent": 10.0}],
    })

    try:
        resolve_frozen_primary_allocation_authority(
            signal_symbol="NFLX",
            vehicle_symbol="NFLU",
            portfolio_allocation_path=portfolio,
            strategy_allocation_path=tmp_path / "unused.json",
        )
    except ValueError as exc:
        assert "paper_trade_mode=true" in str(exc)
    else:
        raise AssertionError("expected paper-only validation failure")

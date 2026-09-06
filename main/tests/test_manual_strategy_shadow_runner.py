import csv
import json
from datetime import date, timedelta
from pathlib import Path

from swing_trade_bot.manual_strategy_shadow_runner import (
    AUTO_PROMOTION_ENABLED,
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_POSITION_CREATION_ENABLED,
    PAPER_TRADE_MODE,
    SHADOW_CAPITAL_RESERVED,
    SHADOW_SIZING_BASIS,
    _primary_share_quantity,
    build_and_write_shadow_strategies,
    run_shadow_strategies,
)


def _registry(path: Path, *, strategy_id: str = "SHADOW_A") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "1.4",
        "paper_trade_mode": True,
        "allocation_authority": "SWING_PORTFOLIO_ALLOCATOR",
        "default_strategy_id": None,
        "strategies": [{
            "strategy_id": strategy_id,
            "name": "Shadow A",
            "timeframe": "1D",
            "rule_logic": "ALL",
            "rules": [{"left": "close", "operator": ">", "right": "ema", "period": 2}],
            "number_of_entries": 1,
            "enabled": True,
            "direction": "LONG",
            "session": "08:30-14:30 CT",
            "confirmation_bars": 1,
            "regime_logic": "ALL",
            "regime_filters": [],
            "normal_exit_logic": "ANY",
            "normal_exit_rules": [{"left": "close", "operator": "<", "right": "ema", "period": 2}],
            "conditional_exits": [],
            "paper_trade_mode": True,
        }],
        "assignments": [{
            "underlying_symbol": "NFLX",
            "strategy_id": strategy_id,
            "assignment_mode": "SHADOW",
            "enabled": True,
            "note": "research",
        }],
    }), encoding="utf-8")


def _mapping(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["underlying_symbol", "leveraged_symbol"])
        writer.writeheader()
        writer.writerow({"underlying_symbol": "NFLX", "leveraged_symbol": "NFLU"})


def _bars(path: Path, closes: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    start = date(2026, 1, 5)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"])
        writer.writeheader()
        for index, close in enumerate(closes):
            writer.writerow({
                "Date": (start + timedelta(days=index)).isoformat(),
                "Open": close,
                "High": close + 1,
                "Low": close - 1,
                "Close": close,
                "Volume": 1000,
            })


def _allocation(path: Path, amount: float = 600.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"allocations": [{"underlying_symbol": "NFLX", "allocated_capital": amount}]}), encoding="utf-8")


def _positions(path: Path, shares: float = 12.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "shares", "market_value", "cost_basis"])
        writer.writeheader()
        writer.writerow({"symbol": "NFLU", "shares": shares, "market_value": shares * 50.0, "cost_basis": shares * 50.0})


def test_primary_share_quantity_is_authoritative_and_sums_matching_rows(tmp_path: Path) -> None:
    positions = tmp_path / "positions.csv"
    positions.parent.mkdir(parents=True, exist_ok=True)
    with positions.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "shares", "market_value", "cost_basis"])
        writer.writeheader()
        writer.writerow({"symbol": "NFLU", "shares": 5.25, "market_value": 0, "cost_basis": 0})
        writer.writerow({"symbol": "NFLU", "shares": 7.25, "market_value": 0, "cost_basis": 0})
        writer.writerow({"symbol": "SOXL", "shares": 99, "market_value": 0, "cost_basis": 0})
    assert _primary_share_quantity(positions, "NFLU") == 12.5


def test_shadow_signals_use_underlying_but_pl_uses_verified_vehicle_and_primary_shares(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.csv"
    allocation = tmp_path / "allocation.json"
    positions = tmp_path / "positions.csv"
    data = tmp_path / "data"
    _registry(registry)
    _mapping(mapping)
    _allocation(allocation, 600.0)
    _positions(positions, 12.0)

    _bars(data / "NFLX.csv", [10, 11, 12, 13, 8, 7])
    _bars(data / "NFLU.csv", [20, 30, 40, 50, 20, 20])

    result = run_shadow_strategies(
        registry_path=registry,
        allocation_path=allocation,
        mapping_path=mapping,
        data_dir=data,
        primary_positions_path=positions,
    )

    row = result["rows"][0]
    assert row["evidence_status"] == "AVAILABLE"
    assert row["simulated_allocation"] == 600.0
    assert row["primary_reference_quantity"] == 12.0
    assert row["shadow_test_quantity"] == 12.0
    assert row["sizing_basis"] == SHADOW_SIZING_BASIS
    assert row["trade_count"] == 1
    # Entry occurs at NFLU $50 and exit at $20. Exact Primary quantity remains
    # 12 shares regardless of the Shadow entry price: 12 * ($20 - $50) = -$360.
    assert row["net_pl"] == -360.0
    assert row["max_drawdown"] <= -360.0
    assert result["shadow_allocation_model"] == "SAME_PRIMARY_SHARE_QUANTITY_SIMULATED_ONLY"
    assert result["normalization_basis"] == "CURRENT_SWING_ALLOCATION"
    assert result["signal_price_authority"] == "UNDERLYING_MARKET_DATA"
    assert result["pnl_price_authority"] == "VERIFIED_MAPPED_VEHICLE_MARKET_DATA"
    entry = result["ledger_rows"][0]
    assert entry["vehicle_symbol"] == "NFLU"
    assert entry["event"] == "ENTRY"
    assert entry["vehicle_price"] == 50.0
    assert entry["shares"] == 12.0
    assert entry["simulated_notional"] == 600.0
    assert result["ledger_rows"][1]["event"] == "EXIT"
    assert result["ledger_rows"][1]["vehicle_price"] == 20.0


def test_shadow_share_quantity_does_not_change_with_entry_price(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.csv"
    allocation = tmp_path / "allocation.json"
    positions = tmp_path / "positions.csv"
    data = tmp_path / "data"
    _registry(registry)
    _mapping(mapping)
    _allocation(allocation, 600.0)
    _positions(positions, 12.5)
    _bars(data / "NFLX.csv", [10, 11, 12, 13, 8, 7])
    _bars(data / "NFLU.csv", [20, 30, 40, 80, 20, 20])

    result = run_shadow_strategies(
        registry_path=registry,
        allocation_path=allocation,
        mapping_path=mapping,
        data_dir=data,
        primary_positions_path=positions,
    )
    entry = result["ledger_rows"][0]
    assert entry["vehicle_price"] == 80.0
    assert entry["shares"] == 12.5
    assert entry["simulated_notional"] == 1000.0
    assert result["rows"][0]["shadow_test_quantity"] == 12.5


def test_missing_mapping_allocation_primary_quantity_and_market_data_fail_closed(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.csv"
    allocation = tmp_path / "allocation.json"
    positions = tmp_path / "positions.csv"
    data = tmp_path / "data"
    _registry(registry)

    no_mapping = run_shadow_strategies(registry_path=registry, allocation_path=allocation, mapping_path=mapping, data_dir=data, primary_positions_path=positions)
    assert no_mapping["rows"][0]["evidence_status"] == "MISSING_VERIFIED_MAPPING"

    _mapping(mapping)
    no_allocation = run_shadow_strategies(registry_path=registry, allocation_path=allocation, mapping_path=mapping, data_dir=data, primary_positions_path=positions)
    assert no_allocation["rows"][0]["evidence_status"] == "MISSING_SWING_ALLOCATION"

    _allocation(allocation)
    no_quantity = run_shadow_strategies(registry_path=registry, allocation_path=allocation, mapping_path=mapping, data_dir=data, primary_positions_path=positions)
    assert no_quantity["rows"][0]["evidence_status"] == "MISSING_PRIMARY_SHARE_QUANTITY"

    _positions(positions)
    no_data = run_shadow_strategies(registry_path=registry, allocation_path=allocation, mapping_path=mapping, data_dir=data, primary_positions_path=positions)
    assert no_data["rows"][0]["evidence_status"] == "MISSING_MARKET_DATA"


def test_runner_writes_separate_ledger_performance_and_assignment_report(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.csv"
    allocation = tmp_path / "allocation.json"
    positions = tmp_path / "positions.csv"
    data = tmp_path / "data"
    ledger = tmp_path / "ledger.json"
    performance = tmp_path / "performance.json"
    assignment_report = tmp_path / "assignment_report.json"
    _registry(registry)
    _mapping(mapping)
    _allocation(allocation)
    _positions(positions, 12.0)
    _bars(data / "NFLX.csv", [10, 11, 12, 13, 8, 7])
    _bars(data / "NFLU.csv", [20, 30, 40, 50, 20, 20])

    build_and_write_shadow_strategies(
        registry_path=registry,
        allocation_path=allocation,
        mapping_path=mapping,
        data_dir=data,
        primary_positions_path=positions,
        ledger_path=ledger,
        performance_path=performance,
        assignment_report_path=assignment_report,
    )

    ledger_payload = json.loads(ledger.read_text(encoding="utf-8"))
    performance_payload = json.loads(performance.read_text(encoding="utf-8"))
    assignment_payload = json.loads(assignment_report.read_text(encoding="utf-8"))
    assert ledger_payload["rows"]
    assert "trade_count" not in ledger_payload["rows"][0]
    assert performance_payload["rows"][0]["trade_count"] == 1
    assert performance_payload["rows"][0]["shadow_test_quantity"] == 12.0
    assert performance_payload["rows"][0]["promotion_recommended"] is False
    shadow = assignment_payload["rows"][0]["shadow_strategies"][0]
    assert shadow["strategy_id"] == "SHADOW_A"
    assert shadow["net_pl"] == -360.0
    assert shadow["promotion_recommended"] is False


def test_shadow_runner_has_no_execution_capital_or_promotion_authority() -> None:
    assert PAPER_TRADE_MODE is True
    assert LIVE_TRADING_ENABLED is False
    assert BROKER_EXECUTION_ENABLED is False
    assert ORDER_PLACEMENT_ENABLED is False
    assert CAPITAL_MOVEMENT_ENABLED is False
    assert PAPER_POSITION_CREATION_ENABLED is False
    assert SHADOW_CAPITAL_RESERVED is False
    assert AUTO_PROMOTION_ENABLED is False

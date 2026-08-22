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


def test_shadow_signals_use_underlying_but_pl_uses_verified_vehicle(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.csv"
    allocation = tmp_path / "allocation.json"
    data = tmp_path / "data"
    _registry(registry)
    _mapping(mapping)
    _allocation(allocation, 600.0)

    _bars(data / "NFLX.csv", [10, 11, 12, 13, 8, 7])
    _bars(data / "NFLU.csv", [20, 30, 40, 50, 20, 20])

    result = run_shadow_strategies(
        registry_path=registry,
        allocation_path=allocation,
        mapping_path=mapping,
        data_dir=data,
    )

    row = result["rows"][0]
    assert row["evidence_status"] == "AVAILABLE"
    assert row["simulated_allocation"] == 600.0
    assert row["trade_count"] == 1
    assert row["net_pl"] == -200.0
    assert row["max_drawdown"] <= -200.0
    assert result["signal_price_authority"] == "UNDERLYING_MARKET_DATA"
    assert result["pnl_price_authority"] == "VERIFIED_MAPPED_VEHICLE_MARKET_DATA"
    assert result["ledger_rows"][0]["vehicle_symbol"] == "NFLU"


def test_missing_mapping_allocation_and_market_data_fail_closed(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.csv"
    allocation = tmp_path / "allocation.json"
    data = tmp_path / "data"
    _registry(registry)

    no_mapping = run_shadow_strategies(registry_path=registry, allocation_path=allocation, mapping_path=mapping, data_dir=data)
    assert no_mapping["rows"][0]["evidence_status"] == "MISSING_VERIFIED_MAPPING"

    _mapping(mapping)
    no_allocation = run_shadow_strategies(registry_path=registry, allocation_path=allocation, mapping_path=mapping, data_dir=data)
    assert no_allocation["rows"][0]["evidence_status"] == "MISSING_SWING_ALLOCATION"

    _allocation(allocation)
    no_data = run_shadow_strategies(registry_path=registry, allocation_path=allocation, mapping_path=mapping, data_dir=data)
    assert no_data["rows"][0]["evidence_status"] == "MISSING_MARKET_DATA"


def test_runner_writes_separate_ledger_performance_and_assignment_report(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.csv"
    allocation = tmp_path / "allocation.json"
    data = tmp_path / "data"
    ledger = tmp_path / "ledger.json"
    performance = tmp_path / "performance.json"
    assignment_report = tmp_path / "assignment_report.json"
    _registry(registry)
    _mapping(mapping)
    _allocation(allocation)
    _bars(data / "NFLX.csv", [10, 11, 12, 13, 8, 7])
    _bars(data / "NFLU.csv", [20, 30, 40, 50, 20, 20])

    build_and_write_shadow_strategies(
        registry_path=registry,
        allocation_path=allocation,
        mapping_path=mapping,
        data_dir=data,
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
    assert performance_payload["rows"][0]["promotion_recommended"] is False
    shadow = assignment_payload["rows"][0]["shadow_strategies"][0]
    assert shadow["strategy_id"] == "SHADOW_A"
    assert shadow["net_pl"] == -200.0
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

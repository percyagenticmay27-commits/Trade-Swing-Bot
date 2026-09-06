import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from swing_trade_bot.mapped_primary_operational_readiness import audit_mapped_primary_operational_readiness


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_intraday(path: Path, *, start_price: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["timestamp", "open", "high", "low", "close", "volume"]
    start = datetime(2026, 8, 24, 9, 30)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for day in range(5):
            session = start + timedelta(days=day)
            if session.weekday() >= 5:
                continue
            for minute in range(390):
                stamp = session + timedelta(minutes=minute)
                price = start_price + day + minute * 0.01
                writer.writerow({
                    "timestamp": stamp.isoformat(),
                    "open": price,
                    "high": price + 0.10,
                    "low": price - 0.10,
                    "close": price + 0.02,
                    "volume": 1000 + minute,
                })


def _config(root: Path) -> None:
    _write_json(root / "configs/frozen_strategy_assignments.json", {
        "schema_version": "1.1",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "symbols": [{
            "symbol": "NVDX",
            "research_status": "NVDA_SIGNAL_MAPPED_NVDX_PAPER_VALIDATION",
            "primary_strategy_id": "NVDX_NVDA_STRATEGY_F_1H_PRIMARY",
            "shadow_strategy_ids": [],
            "shadow_slot_3": None,
        }],
        "strategies": [{
            "strategy_id": "NVDX_NVDA_STRATEGY_F_1H_PRIMARY",
            "name": "NVDA Strategy F",
            "signal_symbol": "NVDA",
            "vehicle_symbol": "NVDX",
            "timeframe": "1H",
            "engine_id": "STRATEGY_F",
            "parameters": {"tema_length": 44, "macd_fast": 17, "macd_slow": 26, "macd_signal": 9, "hma_length": 72},
            "catastrophic_stop_percent": 20.0,
            "assignment_mode": "DIRECT",
            "enabled": True,
            "paper_trade_mode": True,
        }],
    })


def _base_artifacts(root: Path, *, eligible: bool = False, confidence: str = "LOW", allocation: bool = False) -> None:
    _write_intraday(root / "data/intraday/NVDA.csv", start_price=100.0)
    _write_intraday(root / "data/intraday/NVDX.csv", start_price=50.0)
    _write_json(root / "results/paper_ledger/open_positions.json", {"paper_trade_mode": True, "positions": []})
    _write_json(root / "results/paper_ledger/trade_history.json", {"paper_trade_mode": True, "trades": []})
    _write_json(root / "results/paper_ledger/closed_positions.json", {"paper_trade_mode": True, "closed_trades": []})
    _write_json(root / "results/watchlist_report.json", {"paper_trade_mode": True, "rows": [{
        "underlying_symbol": "NVDA", "leveraged_symbol": "NVDX", "capacity_status": "ACTIVE", "watchlist_status": "HIGH"
    }]})
    _write_json(root / "results/committee_allocation_eligibility.json", {
        "paper_trade_mode": True,
        "rows": [{
            "symbol": "NVDA", "underlying_symbol": "NVDA", "leveraged_symbol": "NVDX",
            "opportunity_quality_score": 82.0 if eligible else 68.0,
            "entry_score": 78.0 if eligible else 0.0,
            "thesis_intact": True if eligible else None,
            "eligible_for_allocation": eligible,
            "reason_code": "RANKED_ALLOCATION_ELIGIBLE" if eligible else "OPPORTUNITY_THRESHOLD_NOT_MET",
        }],
        "eligible_symbols": ["NVDA"] if eligible else [],
    })
    _write_json(root / "results/confidence_report.json", {
        "paper_trade_mode": True,
        "confidence_policy_version": "FORWARD_PRIMARY_V1",
        "rows": [{"symbol": "NVDA", "confidence": confidence}],
    })
    allocations = [{"symbol": "NVDA", "allocation_percent": 7.0}] if allocation else [{"symbol": "SGOV", "allocation_percent": 100.0}]
    _write_json(root / "results/portfolio_allocations.json", {"paper_trade_mode": True, "allocations": allocations})


def test_nvdx_readiness_accepts_governed_ineligible_state_with_no_allocation(tmp_path: Path) -> None:
    _config(tmp_path)
    _base_artifacts(tmp_path, eligible=False, confidence="LOW", allocation=False)
    report = audit_mapped_primary_operational_readiness("NVDX", root=tmp_path)
    assert report["runtime_ready"] is True
    assert report["committee_eligible_for_allocation"] is False
    assert report["current_confidence"] == "LOW"
    assert report["forward_primary_trade_count"] == 0
    assert report["current_allocation_percent"] is None
    assert report["open_vehicle_position"] is False
    assert report["daily_cycle_authorized_by_this_audit"] is False


def test_nvdx_readiness_blocks_non_low_confidence_with_zero_primary_trades(tmp_path: Path) -> None:
    _config(tmp_path)
    _base_artifacts(tmp_path, eligible=False, confidence="MEDIUM", allocation=False)
    report = audit_mapped_primary_operational_readiness("NVDX", root=tmp_path)
    assert report["runtime_ready"] is False
    assert "forward_primary_confidence" in report["blockers"]


def test_nvdx_readiness_blocks_allocation_when_committee_is_ineligible(tmp_path: Path) -> None:
    _config(tmp_path)
    _base_artifacts(tmp_path, eligible=False, confidence="LOW", allocation=True)
    report = audit_mapped_primary_operational_readiness("NVDX", root=tmp_path)
    assert report["runtime_ready"] is False
    assert "governed_allocation" in report["blockers"]


def test_nvdx_readiness_blocks_missing_vehicle_intraday_data(tmp_path: Path) -> None:
    _config(tmp_path)
    _base_artifacts(tmp_path, eligible=False, confidence="LOW", allocation=False)
    (tmp_path / "data/intraday/NVDX.csv").unlink()
    report = audit_mapped_primary_operational_readiness("NVDX", root=tmp_path)
    assert report["runtime_ready"] is False
    assert "market_data" in report["blockers"]


def test_nvdx_readiness_blocks_foreign_strategy_open_position(tmp_path: Path) -> None:
    _config(tmp_path)
    _base_artifacts(tmp_path, eligible=False, confidence="LOW", allocation=False)
    _write_json(tmp_path / "results/paper_ledger/open_positions.json", {
        "paper_trade_mode": True,
        "positions": [{"symbol": "NVDX", "active_strategy": "OLD_STRATEGY", "shares": 1.0}],
    })
    report = audit_mapped_primary_operational_readiness("NVDX", root=tmp_path)
    assert report["runtime_ready"] is False
    assert "paper_ledger" in report["blockers"]

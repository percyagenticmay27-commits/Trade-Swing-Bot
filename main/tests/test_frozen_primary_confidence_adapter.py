import json
import math
import unittest
import uuid
from pathlib import Path

from swing_trade_bot.frozen_primary_confidence_adapter import (
    EVIDENCE_SCOPE,
    build_and_write_forward_primary_confidence_metrics,
    build_forward_primary_confidence_metrics,
)


class FrozenPrimaryConfidenceAdapterTests(unittest.TestCase):
    def test_only_current_primary_completed_vehicle_trades_are_counted(self) -> None:
        with temp_dir() as root:
            config = root / "assignments.json"
            closed = root / "closed_positions.json"
            watchlist = root / "watchlist_report.json"
            write_config(config)
            write_closed(
                closed,
                [
                    closed_trade("NFLU", "NFLU_NFLX_ZERO_LAG_1H_PRIMARY", 10.0),
                    closed_trade("NFLU", "NFLU_NFLX_ZERO_LAG_1H_PRIMARY", -5.0),
                    closed_trade("NFLU", "NFLU_NFLX_STRATEGY_F_1H_SHADOW_1", 100.0),
                    closed_trade("NFLU", "LEGACY_STRATEGY_A", 50.0),
                    closed_trade("NFLX", "NFLU_NFLX_ZERO_LAG_1H_PRIMARY", 50.0),
                ],
            )
            write_watchlist(watchlist)

            rows = build_forward_primary_confidence_metrics(
                closed_positions_path=closed,
                config_path=config,
                watchlist_path=watchlist,
            )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.symbol, "NFLX")
        self.assertEqual(row.vehicle_symbol, "NFLU")
        self.assertEqual(row.signal_symbol, "NFLX")
        self.assertEqual(row.strategy_id, "NFLU_NFLX_ZERO_LAG_1H_PRIMARY")
        self.assertEqual(row.number_of_trades, 2)
        self.assertEqual(row.win_rate, 50.0)
        self.assertEqual(row.profit_factor, 2.0)
        self.assertEqual(row.realized_pnl, 5.0)

    def test_no_forward_primary_trades_remains_missing_performance(self) -> None:
        with temp_dir() as root:
            config = root / "assignments.json"
            closed = root / "closed_positions.json"
            write_config(config)
            write_closed(closed, [closed_trade("NFLU", "LEGACY_STRATEGY_A", 50.0)])

            rows = build_forward_primary_confidence_metrics(
                closed_positions_path=closed,
                config_path=config,
                watchlist_path=None,
            )

        row = rows[0]
        self.assertEqual(row.symbol, "NFLX")
        self.assertEqual(row.number_of_trades, 0)
        self.assertIsNone(row.win_rate)
        self.assertIsNone(row.profit_factor)

    def test_all_wins_use_infinite_profit_factor_without_invalid_json(self) -> None:
        with temp_dir() as root:
            config = root / "assignments.json"
            closed = root / "closed_positions.json"
            csv_path = root / "metrics.csv"
            json_path = root / "metrics.json"
            write_config(config)
            write_closed(
                closed,
                [
                    closed_trade("NFLU", "NFLU_NFLX_ZERO_LAG_1H_PRIMARY", 5.0),
                    closed_trade("NFLU", "NFLU_NFLX_ZERO_LAG_1H_PRIMARY", 7.0),
                ],
            )

            rows = build_and_write_forward_primary_confidence_metrics(
                closed_positions_path=closed,
                config_path=config,
                watchlist_path=None,
                metrics_csv_path=csv_path,
                provenance_json_path=json_path,
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            csv_text = csv_path.read_text(encoding="utf-8")

        self.assertTrue(math.isinf(rows[0].profit_factor))
        self.assertEqual(payload["rows"][0]["profit_factor"], "INF")
        self.assertIn(",inf,", csv_text)
        self.assertEqual(payload["evidence_scope"], EVIDENCE_SCOPE)
        self.assertFalse(payload["historical_backtest_evidence_allowed"])
        self.assertFalse(payload["shadow_performance_allowed"])
        self.assertFalse(payload["frozen_strategy_performance_allowed"])

    def test_watchlist_leveraged_mapping_resolves_underlying_allocator_key(self) -> None:
        with temp_dir() as root:
            config = root / "assignments.json"
            closed = root / "closed_positions.json"
            watchlist = root / "watchlist_report.json"
            write_config(config, signal_symbol="ALT_SIGNAL")
            write_closed(closed, [])
            write_watchlist(watchlist, underlying="NFLX", leveraged="NFLU")

            rows = build_forward_primary_confidence_metrics(
                closed_positions_path=closed,
                config_path=config,
                watchlist_path=watchlist,
            )

        self.assertEqual(rows[0].symbol, "NFLX")
        self.assertEqual(rows[0].signal_symbol, "ALT_SIGNAL")
        self.assertEqual(rows[0].vehicle_symbol, "NFLU")

    def test_non_paper_closed_positions_fail_closed(self) -> None:
        with temp_dir() as root:
            config = root / "assignments.json"
            closed = root / "closed_positions.json"
            write_config(config)
            closed.write_text(json.dumps({"paper_trade_mode": False, "closed_trades": []}), encoding="utf-8")

            with self.assertRaises(ValueError):
                build_forward_primary_confidence_metrics(
                    closed_positions_path=closed,
                    config_path=config,
                    watchlist_path=None,
                )


def write_config(path: Path, *, signal_symbol: str = "NFLX") -> None:
    payload = {
        "schema_version": "1.1",
        "paper_trade_mode": True,
        "strategy_id": "SWING-001",
        "symbols": [
            {
                "symbol": "NFLU",
                "research_status": "NFLX_SIGNAL_MAPPED_NFLU_PAPER_VALIDATION",
                "primary_strategy_id": "NFLU_NFLX_ZERO_LAG_1H_PRIMARY",
                "shadow_strategy_ids": ["NFLU_NFLX_STRATEGY_F_1H_SHADOW_1"],
                "shadow_slot_3": None,
            }
        ],
        "strategies": [
            {
                "strategy_id": "NFLU_NFLX_ZERO_LAG_1H_PRIMARY",
                "name": "Primary",
                "signal_symbol": signal_symbol,
                "vehicle_symbol": "NFLU",
                "timeframe": "1H",
                "engine_id": "ZERO_LAG",
                "parameters": {"length": 50, "multiplier": 2.5, "adx_min": 20.0},
                "catastrophic_stop_percent": 20.0,
                "assignment_mode": "DIRECT",
                "enabled": True,
                "paper_trade_mode": True,
            },
            {
                "strategy_id": "NFLU_NFLX_STRATEGY_F_1H_SHADOW_1",
                "name": "Shadow",
                "signal_symbol": signal_symbol,
                "vehicle_symbol": "NFLU",
                "timeframe": "1H",
                "engine_id": "STRATEGY_F",
                "parameters": {"hma_length": 150, "chop_max": 60.0},
                "catastrophic_stop_percent": 20.0,
                "assignment_mode": "SHADOW",
                "enabled": True,
                "paper_trade_mode": True,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_closed(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"schema_version": "1.0", "paper_trade_mode": True, "closed_trades": rows}),
        encoding="utf-8",
    )


def closed_trade(symbol: str, strategy_id: str, realized: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "active_strategy": strategy_id,
        "realized_pnl": realized,
    }


def write_watchlist(path: Path, *, underlying: str = "NFLX", leveraged: str = "NFLU") -> None:
    path.write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "rows": [
                    {
                        "underlying_symbol": underlying,
                        "leveraged_symbol": leveraged,
                        "watchlist_rank": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class TempDir:
    def __init__(self) -> None:
        self.path = Path.cwd() / f"forward_primary_confidence_test_{uuid.uuid4().hex}"

    def __enter__(self) -> Path:
        self.path.mkdir()
        return self.path

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        for child in sorted(self.path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            else:
                child.rmdir()
        self.path.rmdir()


def temp_dir() -> TempDir:
    return TempDir()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from swing_trade_bot.swing_trade_analytics_report import (
    BROKER_EXECUTION_ENABLED,
    CAPITAL_MOVEMENT_ENABLED,
    DIRECT_DATABASE_WRITES,
    LIVE_TRADING_ENABLED,
    ORDER_PLACEMENT_ENABLED,
    PAPER_TRADE_MODE,
    build_swing_trade_analytics_report,
    write_swing_trade_analytics_report,
)


def _payload() -> dict:
    return {
        "strategy_id": "SWING-001",
        "generated_at": "2026-08-15T04:56:08Z",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "capital_movement_enabled": False,
        "direct_database_writes": False,
        "trade_analytics": {
            "max_drawdown_policy": "AUTHORITATIVE_POSITION_HISTORY_ONLY",
            "max_drawdown_inference_allowed": False,
            "open_position_count": 1,
            "closed_position_count": 1,
            "open_positions": [
                {
                    "symbol": "SOXL",
                    "entry_date": "2026-08-04",
                    "entry_price": 139.899993896484,
                    "current_price": 143.264297485352,
                    "shares": 8.04145854,
                    "cost_basis": 1125.0,
                    "market_value": 1152.05,
                    "unrealized_pnl": 27.05,
                    "unrealized_pnl_percent": 2.404444,
                    "max_drawdown_amount": 82.42,
                    "max_drawdown_percent": 7.308378,
                    "active_strategy": "Strategy A",
                    "position_status": "OPEN",
                }
            ],
            "closed_positions": [
                {
                    "symbol": "TQQQ",
                    "entry_date": "2026-08-01",
                    "entry_price": 70.0,
                    "exit_date": "2026-08-11",
                    "exit_price": 75.0,
                    "shares": 2.0,
                    "cost_basis": 140.0,
                    "proceeds": 150.0,
                    "realized_pnl": 10.0,
                    "realized_pnl_percent": 7.142857,
                    "max_drawdown_amount": 8.0,
                    "max_drawdown_percent": 5.0,
                    "holding_days": 10,
                    "active_strategy": "Strategy A",
                    "position_status": "CLOSED",
                    "exit_reason": "TARGET_EXIT",
                }
            ],
        },
    }


class SwingTradeAnalyticsReportTests(unittest.TestCase):
    def test_builds_open_and_closed_position_performance_rows(self) -> None:
        report = build_swing_trade_analytics_report(_payload())
        self.assertEqual(report["open_position_count"], 1)
        self.assertEqual(report["closed_position_count"], 1)

        open_row = report["open_positions"][0]
        self.assertEqual(open_row["symbol"], "SOXL")
        self.assertEqual(open_row["current_or_exit_value"], 1152.05)
        self.assertEqual(open_row["gain_loss_amount"], 27.05)
        self.assertEqual(open_row["gain_loss_percent"], 2.404444)
        self.assertEqual(open_row["max_drawdown_percent"], 7.308378)
        self.assertEqual(open_row["days_held"], 11)
        self.assertNotIn("exit_date", open_row)
        self.assertNotIn("exit_price", open_row)
        self.assertNotIn("exit_reason", open_row)

        closed_row = report["closed_positions"][0]
        self.assertEqual(closed_row["current_or_exit_value"], 150.0)
        self.assertEqual(closed_row["gain_loss_amount"], 10.0)
        self.assertEqual(closed_row["gain_loss_percent"], 7.142857)
        self.assertEqual(closed_row["days_held"], 10)
        self.assertEqual(closed_row["exit_reason"], "TARGET_EXIT")

    def test_open_position_exit_evidence_is_rejected(self) -> None:
        payload = _payload()
        payload["trade_analytics"]["open_positions"][0]["exit_price"] = 150.0
        with self.assertRaisesRegex(ValueError, "fabricated exit evidence"):
            build_swing_trade_analytics_report(payload)

    def test_inferred_drawdown_policy_is_rejected(self) -> None:
        payload = _payload()
        payload["trade_analytics"]["max_drawdown_inference_allowed"] = True
        with self.assertRaisesRegex(ValueError, "prohibit"):
            build_swing_trade_analytics_report(payload)

    def test_buy_only_evidence_keeps_closed_rows_empty(self) -> None:
        payload = _payload()
        payload["trade_analytics"]["closed_position_count"] = 0
        payload["trade_analytics"]["closed_positions"] = []
        report = build_swing_trade_analytics_report(payload)
        self.assertEqual(report["closed_position_count"], 0)
        self.assertEqual(report["closed_positions"], [])

    def test_json_csv_and_markdown_are_published(self) -> None:
        report = build_swing_trade_analytics_report(_payload())
        with TemporaryDirectory() as directory:
            json_path, csv_path, md_path = write_swing_trade_analytics_report(report, directory)
            stored = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["report_id"], "SWING-TRADE-ANALYTICS")
            rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
            self.assertEqual(len(rows), 2)
            markdown = md_path.read_text(encoding="utf-8")
            self.assertIn("Swing Trade Analytics / Position Performance", markdown)
            self.assertIn("SOXL", markdown)
            self.assertFalse((Path(directory) / ".swing_trade_analytics_report.json.tmp").exists())

    def test_paper_safety_is_locked(self) -> None:
        self.assertTrue(PAPER_TRADE_MODE)
        self.assertFalse(LIVE_TRADING_ENABLED)
        self.assertFalse(BROKER_EXECUTION_ENABLED)
        self.assertFalse(ORDER_PLACEMENT_ENABLED)
        self.assertFalse(CAPITAL_MOVEMENT_ENABLED)
        self.assertFalse(DIRECT_DATABASE_WRITES)


if __name__ == "__main__":
    unittest.main()

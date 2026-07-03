import csv
import json
import unittest
import uuid
from pathlib import Path

from swing_trade_bot.portfolio_manager import (
    CurrentPosition,
    PortfolioManager,
    TargetAllocation,
    build_portfolio_manager_report,
    format_rebalance_actions,
    write_manager_outputs,
)


class PortfolioManagerTests(unittest.TestCase):
    def test_buy_sell_hold_and_move_to_sgov_actions(self) -> None:
        result = PortfolioManager(tolerance_percent=0.01).rebalance(
            [
                position("NEBX", 5_000),
                position("IONL", 7_000),
                position("SOXL", 25_000),
                position("SGOV", 63_000),
            ],
            [
                target("NEBX", 10),
                target("IONL", 0),
                target("SOXL", 25),
                target("SGOV", 65, cash_equivalent="SGOV"),
            ],
        )
        actions = {row.symbol: row for row in result.actions}

        self.assertEqual(actions["NEBX"].action, "BUY")
        self.assertEqual(actions["IONL"].action, "SELL")
        self.assertEqual(actions["SOXL"].action, "HOLD")
        self.assertEqual(actions["SGOV"].action, "MOVE_TO_SGOV")
        self.assertEqual(actions["NEBX"].difference, 5.0)
        self.assertEqual(actions["IONL"].estimated_cash_change, -7000.0)

    def test_all_unallocated_capital_is_tracked_as_sgov_reserve(self) -> None:
        result = PortfolioManager().rebalance(
            [position("SOXL", 25_000), position("SGOV", 75_000)],
            [target("SOXL", 25), target("SGOV", 75, cash_equivalent="SGOV")],
        )

        self.assertEqual(result.cash_reserve, 75_000.0)
        self.assertEqual(result.sgov_reserve, 75_000.0)

    def test_writes_rebalance_and_manager_reports(self) -> None:
        result = PortfolioManager().rebalance(
            [position("SOXL", 20_000), position("SGOV", 80_000)],
            [target("SOXL", 25), target("SGOV", 75, cash_equivalent="SGOV")],
        )
        with workspace_temp_dir() as directory:
            actions_csv, actions_json, manager_csv = write_manager_outputs(directory, result)
            with actions_csv.open(newline="", encoding="utf-8") as input_file:
                actions = list(csv.DictReader(input_file))
            payload = json.loads(actions_json.read_text(encoding="utf-8"))
            with manager_csv.open(newline="", encoding="utf-8") as input_file:
                report = list(csv.DictReader(input_file))

        self.assertEqual(actions[0]["symbol"], "SGOV")
        self.assertTrue(payload["paper_trade_mode"])
        self.assertIn("allocation_after", report[0])

    def test_build_report_reads_csv_inputs(self) -> None:
        with workspace_temp_dir() as directory:
            current = directory / "current.csv"
            target_path = directory / "target.csv"
            current.write_text(
                "symbol,shares,market_value,cost_basis\nSOXL,10,20000,15000\nSGOV,80,80000,80000\n",
                encoding="utf-8",
            )
            target_path.write_text(
                "symbol,confidence_level,active_strategy,rank,allocation_percent,theme,theme_allocation,cash_equivalent\n"
                "SOXL,HIGH,Strategy A,,25,Semiconductors,25,\n"
                "SGOV,RESERVE,,,75,Cash Equivalent,75,SGOV\n",
                encoding="utf-8",
            )

            result = build_portfolio_manager_report(
                current_portfolio_path=current,
                target_portfolio_path=target_path,
                output_dir=directory,
            )

        self.assertEqual(result.total_market_value, 100_000.0)
        self.assertTrue(any(action.action == "BUY" for action in result.actions))

    def test_format_rebalance_actions_contains_action_labels(self) -> None:
        result = PortfolioManager().rebalance(
            [position("SOXL", 20_000), position("SGOV", 80_000)],
            [target("SOXL", 25), target("SGOV", 75, cash_equivalent="SGOV")],
        )

        self.assertIn("BUY", format_rebalance_actions(result.actions))

    def test_live_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PortfolioManager(paper_trade_mode=False)


def position(symbol: str, market_value: float) -> CurrentPosition:
    return CurrentPosition(symbol=symbol, shares=1.0, market_value=market_value, cost_basis=market_value)


def target(symbol: str, allocation: float, *, cash_equivalent: str = "") -> TargetAllocation:
    return TargetAllocation(symbol=symbol, allocation_percent=allocation, cash_equivalent=cash_equivalent)


def workspace_temp_dir():
    class WorkspaceTempDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"portfolio_manager_test_{uuid.uuid4().hex}"

        def __enter__(self) -> Path:
            self.path.mkdir()
            return self.path

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for child in self.path.iterdir():
                child.unlink()
            self.path.rmdir()

    return WorkspaceTempDir()


if __name__ == "__main__":
    unittest.main()

import csv
import json
import unittest
import uuid
from pathlib import Path

from swing_trade_bot.executive_dashboard import (
    build_executive_dashboard,
    format_executive_dashboard_markdown,
)


class ExecutiveDashboardTests(unittest.TestCase):
    def test_missing_optional_files_warn_without_failure(self) -> None:
        with temp_dir() as directory:
            write_minimum_required_outputs(directory)
            dashboard = build_executive_dashboard(directory)

        self.assertTrue(dashboard.paper_trade_mode)
        self.assertGreater(dashboard.summary.warning_count, 0)
        self.assertTrue(any("Missing optional" in warning for warning in dashboard.warnings))
        self.assertFalse(any("Missing required" in warning for warning in dashboard.warnings))

    def test_missing_required_files_create_risk_flag(self) -> None:
        with temp_dir() as directory:
            dashboard = build_executive_dashboard(directory)

        self.assertTrue(any("Missing required" in warning for warning in dashboard.warnings))
        self.assertIn("Dashboard is incomplete because required outputs are missing", dashboard.risk_flags)

    def test_summary_metrics_are_computed_from_existing_outputs(self) -> None:
        with temp_dir() as directory:
            write_minimum_required_outputs(directory)
            dashboard = build_executive_dashboard(directory)

        self.assertEqual(dashboard.summary.sgov_reserve_percent, 35.0)
        self.assertEqual(dashboard.summary.allocated_percent, 65.0)
        self.assertEqual(dashboard.summary.high_confidence_count, 1)
        self.assertEqual(dashboard.summary.strategy_b_count, 1)
        self.assertEqual(dashboard.summary.watchlist_count, 1)

    def test_dashboard_outputs_are_written(self) -> None:
        with temp_dir() as directory:
            write_minimum_required_outputs(directory)
            dashboard = build_executive_dashboard(directory)
            payload = json.loads((directory / "executive_dashboard.json").read_text(encoding="utf-8"))
            markdown = (directory / "executive_dashboard.md").read_text(encoding="utf-8")

        self.assertTrue(payload["paper_trade_mode"])
        self.assertIn("Executive Dashboard", markdown)
        self.assertIn("Suggested Actions", format_executive_dashboard_markdown(dashboard))

    def test_live_mode_is_rejected(self) -> None:
        with temp_dir() as directory:
            with self.assertRaises(ValueError):
                build_executive_dashboard(directory, paper_trade_mode=False)


def write_minimum_required_outputs(directory: Path) -> None:
    (directory / "portfolio_allocations.json").write_text(
        json.dumps(
            {
                "paper_trade_mode": True,
                "sgov_allocation": 35.0,
                "allocations": [
                    {"symbol": "SOXL", "allocation_percent": 25.0, "theme": "Semiconductors", "theme_allocation": 25.0},
                    {"symbol": "SGOV", "allocation_percent": 35.0, "theme": "Cash Equivalent", "theme_allocation": 35.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    write_csv(directory / "portfolio_manager_report.csv", ["symbol", "signal"], [["SOXL", "HOLD"]])
    (directory / "strategy_comparison.json").write_text(json.dumps({"paper_trade_mode": True, "rows": []}), encoding="utf-8")
    write_csv(directory / "strategy_recommendations.csv", ["symbol", "active_strategy"], [["SOXL", "Strategy B"]])
    (directory / "confidence_report.json").write_text(json.dumps({"paper_trade_mode": True, "rows": [{"symbol": "SOXL", "confidence": "HIGH"}]}), encoding="utf-8")
    (directory / "watchlist_report.json").write_text(json.dumps({"paper_trade_mode": True, "rows": [{"underlying_symbol": "SOXL", "watchlist_status": "WATCHLIST"}]}), encoding="utf-8")


def write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)


def temp_dir():
    class TempDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"executive_dashboard_test_{uuid.uuid4().hex}"

        def __enter__(self) -> Path:
            self.path.mkdir()
            return self.path

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for child in self.path.iterdir():
                child.unlink()
            self.path.rmdir()

    return TempDir()


if __name__ == "__main__":
    unittest.main()

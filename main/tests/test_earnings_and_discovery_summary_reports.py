import json
import unittest
import uuid
from datetime import date
from pathlib import Path

from swing_trade_bot.discovery_summary_reports import build_discovery_summary_reports
from swing_trade_bot.earnings_report import build_earnings_report


class EarningsAndDiscoverySummaryReportTests(unittest.TestCase):
    def test_earnings_report_writes_csv_json_and_markdown(self) -> None:
        with temp_dir() as directory:
            input_path = directory / "earnings.csv"
            input_path.write_text("symbol,earnings_date\nSOXL,2026-07-08\n", encoding="utf-8")
            rows = build_earnings_report(input_path, directory, as_of=date(2026, 7, 3))
            payload = json.loads((directory / "earnings_report.json").read_text(encoding="utf-8"))

        self.assertEqual(rows[0].earnings_risk_level, "HIGH")
        self.assertTrue(payload["paper_trade_mode"])

    def test_discovery_summary_reports_write_theme_and_source_files(self) -> None:
        with temp_dir() as directory:
            watchlist = directory / "watchlist_report.json"
            watchlist.write_text(
                json.dumps(
                    {
                        "rows": [
                            {"underlying_symbol": "SOXL", "themes": "Semiconductors", "theme_momentum_score": 80, "source_confluence_level": "HIGH_PRIORITY_WATCHLIST"},
                            {"underlying_symbol": "TQQQ", "themes": "Cloud Computing", "theme_momentum_score": 60, "source_confluence_level": "WATCHLIST"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            theme_rows, confluence_rows = build_discovery_summary_reports(watchlist, directory)
            theme_payload = json.loads((directory / "theme_momentum.json").read_text(encoding="utf-8"))
            source_payload = json.loads((directory / "source_confluence.json").read_text(encoding="utf-8"))

        self.assertEqual(theme_rows[0].theme, "Semiconductors")
        self.assertEqual(confluence_rows[0].symbol_count, 1)
        self.assertTrue(theme_payload["paper_trade_mode"])
        self.assertTrue(source_payload["paper_trade_mode"])

    def test_live_modes_are_rejected(self) -> None:
        with temp_dir() as directory:
            input_path = directory / "earnings.csv"
            input_path.write_text("symbol,earnings_date\nSOXL,2026-07-08\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_earnings_report(input_path, directory, paper_trade_mode=False)
            with self.assertRaises(ValueError):
                build_discovery_summary_reports(input_path, directory, paper_trade_mode=False)


def temp_dir():
    class TempDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"summary_reports_test_{uuid.uuid4().hex}"

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

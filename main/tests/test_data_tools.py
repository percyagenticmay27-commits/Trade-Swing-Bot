import unittest
import uuid
from contextlib import redirect_stdout
from collections.abc import Iterator
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from swing_trade_bot.data_tools import (
    REQUIRED_SYMBOLS,
    format_validation_summary,
    main,
    validate_data_directory,
)


class DataToolsTests(unittest.TestCase):
    def test_validates_required_ohlcv_files(self) -> None:
        with temp_data_dir() as directory:
            data_dir = Path(directory)
            for symbol in REQUIRED_SYMBOLS:
                write_csv(data_dir / f"{symbol}.csv", bars=252)

            results = validate_data_directory(data_dir)
            summary = format_validation_summary(results)

        self.assertTrue(all(result.is_valid for result in results))
        self.assertIn("Missing files: none", summary)
        self.assertIn("SOXL", summary)
        soxl = next(result for result in results if result.symbol == "SOXL")
        self.assertEqual(soxl.row_count, 252)
        self.assertEqual(soxl.start_date, date(2025, 1, 1))
        self.assertEqual(soxl.end_date, date(2025, 9, 9))

    def test_reports_missing_required_files(self) -> None:
        with temp_data_dir() as directory:
            results = validate_data_directory(Path(directory))

        missing = [result.symbol for result in results if not result.exists]
        self.assertEqual(missing, list(REQUIRED_SYMBOLS))
        self.assertFalse(all(result.is_valid for result in results))

    def test_reports_missing_columns(self) -> None:
        with temp_data_dir() as directory:
            data_dir = Path(directory)
            for symbol in REQUIRED_SYMBOLS:
                write_csv(data_dir / f"{symbol}.csv", bars=252)
            (data_dir / "SOXL.csv").write_text("date,close,volume\n2025-01-01,100,1000\n")

            result = next(item for item in validate_data_directory(data_dir) if item.symbol == "SOXL")

        self.assertIn("header: missing columns: open, high, low", result.invalid_rows)

    def test_reports_invalid_rows(self) -> None:
        with temp_data_dir() as directory:
            data_dir = Path(directory)
            for symbol in REQUIRED_SYMBOLS:
                write_csv(data_dir / f"{symbol}.csv", bars=252)
            write_csv(
                data_dir / "SOXL.csv",
                bars=252,
                overrides={
                    1: {"date": "2025-01-01"},
                    2: {"open": ""},
                    3: {"high": "99"},
                    4: {"low": "105"},
                    5: {"volume": "-1"},
                    6: {"close": "0"},
                },
            )

            result = next(item for item in validate_data_directory(data_dir) if item.symbol == "SOXL")

        issues = "\n".join(result.invalid_rows)
        self.assertIn("row 3: date is not chronological", issues)
        self.assertIn("row 4: missing open", issues)
        self.assertIn("row 5: high must be >= open and close", issues)
        self.assertIn("row 6: low must be <= open and close", issues)
        self.assertIn("row 7: volume must be non-negative", issues)
        self.assertIn("row 8: close must be positive", issues)

    def test_requires_at_least_252_bars(self) -> None:
        with temp_data_dir() as directory:
            data_dir = Path(directory)
            for symbol in REQUIRED_SYMBOLS:
                write_csv(data_dir / f"{symbol}.csv", bars=252)
            write_csv(data_dir / "SOXL.csv", bars=251)

            result = next(item for item in validate_data_directory(data_dir) if item.symbol == "SOXL")

        self.assertIn("file: expected at least 252 rows, found 251", result.invalid_rows)

    def test_cli_exits_nonzero_for_invalid_data(self) -> None:
        with temp_data_dir() as directory:
            with patch("sys.argv", ["data_tools", "--data-dir", directory]):
                with redirect_stdout(StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        main()

        self.assertEqual(raised.exception.code, 1)


def temp_data_dir() -> Iterator[str]:
    class TempDataDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"data_tools_test_{uuid.uuid4().hex}"

        def __enter__(self) -> str:
            self.path.mkdir()
            return str(self.path)

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for child in self.path.iterdir():
                child.unlink()
            self.path.rmdir()

    return TempDataDir()


def write_csv(
    path: Path,
    *,
    bars: int,
    overrides: dict[int, dict[str, str]] | None = None,
) -> None:
    start = date(2025, 1, 1)
    rows = ["date,open,high,low,close,volume"]
    overrides = overrides or {}
    for index in range(bars):
        current = start + timedelta(days=index)
        row = {
            "date": current.isoformat(),
            "open": "100",
            "high": "102",
            "low": "99",
            "close": "101",
            "volume": "1000",
        }
        row.update(overrides.get(index, {}))
        rows.append(
            ",".join(
                [
                    row["date"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                ]
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

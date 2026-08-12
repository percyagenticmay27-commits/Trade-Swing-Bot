import unittest
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from swing_trade_bot.data_download import (
    build_historical_data,
    format_download_summary,
)
from swing_trade_bot.data_tools import REQUIRED_SYMBOLS


class DataDownloadTests(unittest.TestCase):
    def test_yahoo_download_writes_required_csv_and_runs_validation(self) -> None:
        with temp_data_dir() as directory:
            data_dir = Path(directory)
            with patch("swing_trade_bot.data_download.urlopen", return_value=FakeResponse(provider_csv(252))):
                run = build_historical_data(data_dir, symbols=REQUIRED_SYMBOLS)

            soxl = (data_dir / "SOXL.csv").read_text(encoding="utf-8")
            summary = format_download_summary(run.summaries)

        self.assertTrue(run.validation_ok)
        self.assertIn("date,open,high,low,close,volume", soxl)
        self.assertIn("SOXL", summary)
        self.assertTrue(all(item.source == "yahoo" for item in run.summaries))
        self.assertTrue(all(item.updated for item in run.summaries))

    def test_stooq_is_used_when_yahoo_is_unavailable(self) -> None:
        with temp_data_dir() as directory:
            with patched_validation():
                with patch(
                    "swing_trade_bot.data_download.urlopen",
                    side_effect=[URLError("down"), URLError("down"), FakeResponse(provider_csv(2))],
                ):
                    run = build_historical_data(Path(directory), symbols=("SOXL",))

        self.assertEqual(run.summaries[0].source, "stooq")
        self.assertEqual(run.summaries[0].rows, 2)
        self.assertIsNone(run.summaries[0].error)

    def test_yahoo_chart_is_used_when_yahoo_csv_is_unavailable(self) -> None:
        with temp_data_dir() as directory:
            with patched_validation():
                with patch(
                    "swing_trade_bot.data_download.urlopen",
                    side_effect=[URLError("down"), FakeResponse(chart_json(2))],
                ):
                    run = build_historical_data(Path(directory), symbols=("SOXL",))

        self.assertEqual(run.summaries[0].source, "yahoo_chart")
        self.assertEqual(run.summaries[0].rows, 2)
        self.assertIsNone(run.summaries[0].error)

    def test_csv_import_fallback_is_used_after_provider_failures(self) -> None:
        with temp_data_dir() as data_directory, temp_data_dir() as import_directory:
            import_dir = Path(import_directory)
            (import_dir / "SOXL.csv").write_text(provider_csv(3), encoding="utf-8")
            with patched_validation():
                with patch("swing_trade_bot.data_download.urlopen", side_effect=URLError("down")):
                    run = build_historical_data(
                        Path(data_directory),
                        import_dir=import_dir,
                        symbols=("SOXL",),
                    )

            written = (Path(data_directory) / "SOXL.csv").read_text(encoding="utf-8")

        self.assertEqual(run.summaries[0].source, "historical_csv")
        self.assertEqual(run.summaries[0].data_source, "HISTORICAL_CSV_FALLBACK")
        self.assertFalse(run.summaries[0].is_stale)
        self.assertIn("2025-01-03", written)

    def test_merge_skips_duplicate_dates(self) -> None:
        with temp_data_dir() as directory:
            data_dir = Path(directory)
            (data_dir / "SOXL.csv").write_text(provider_csv(1), encoding="utf-8")
            with patched_validation():
                with patch(
                    "swing_trade_bot.data_download.urlopen",
                    return_value=FakeResponse(provider_csv(2)),
                ):
                    run = build_historical_data(data_dir, symbols=("SOXL",))

            rows = (data_dir / "SOXL.csv").read_text(encoding="utf-8").strip().splitlines()

        self.assertEqual(len(rows), 3)
        self.assertEqual(run.summaries[0].rows, 2)
        self.assertTrue(run.summaries[0].updated)

    def test_unavailable_ticker_reports_error_and_continues(self) -> None:
        with temp_data_dir() as directory:
            with patched_validation():
                with patch("swing_trade_bot.data_download.urlopen", side_effect=URLError("down")):
                    run = build_historical_data(Path(directory), symbols=("SOXL", "TQQQ"))

        self.assertEqual([item.symbol for item in run.summaries], ["SOXL", "TQQQ"])
        self.assertTrue(all(item.error for item in run.summaries))
        self.assertTrue(all(item.rows == 0 for item in run.summaries))


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return self.text.encode("utf-8")


def patched_validation() -> Iterator[None]:
    class PatchedValidation:
        def __enter__(self) -> None:
            self.validation = patch("swing_trade_bot.data_download.validate_data_directory", return_value=[])
            self.formatter = patch("swing_trade_bot.data_download.format_validation_summary", return_value="OK")
            self.validation.__enter__()
            self.formatter.__enter__()

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            self.formatter.__exit__(exc_type, exc, traceback)
            self.validation.__exit__(exc_type, exc, traceback)

    return PatchedValidation()


def temp_data_dir() -> Iterator[str]:
    class TempDataDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"data_download_test_{uuid.uuid4().hex}"

        def __enter__(self) -> str:
            self.path.mkdir()
            return str(self.path)

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for child in self.path.iterdir():
                child.unlink()
            self.path.rmdir()

    return TempDataDir()


def provider_csv(rows: int) -> str:
    start = date(2025, 1, 1)
    lines = ["Date,Open,High,Low,Close,Adj Close,Volume"]
    for index in range(rows):
        current = start + timedelta(days=index)
        open_price = 100 + index
        lines.append(
            ",".join(
                [
                    current.isoformat(),
                    str(open_price),
                    str(open_price + 2),
                    str(open_price - 1),
                    str(open_price + 1),
                    str(open_price + 1),
                    str(1000 + index),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def chart_json(rows: int) -> str:
    timestamps = [
        1735689600 + (index * 86_400)
        for index in range(rows)
    ]
    return (
        '{"chart":{"result":[{"timestamp":'
        + str(timestamps)
        + ',"indicators":{"quote":[{"open":[100,101],"high":[102,103],"low":[99,100],'
        + '"close":[101,102],"volume":[1000,1001]}]}}],"error":null}}'
    )


if __name__ == "__main__":
    unittest.main()

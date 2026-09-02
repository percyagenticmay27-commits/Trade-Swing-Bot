import json
import unittest
import uuid
from collections.abc import Iterator
from pathlib import Path

from swing_trade_bot.confidence_engine import build_confidence_report


class ConfidenceEngineTests(unittest.TestCase):
    def test_low_confidence_promotion_requires_metrics_trades_and_days(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("SOXL", 40.0, 1.50, 15)])
            write_bars(root / "SOXL.csv", 252)

            rows = build_confidence_report(
                scores_path,
                root,
                output_dir=root,
                starting_confidence={"SOXL": "LOW"},
            )

        soxl = by_symbol(rows, "SOXL")
        self.assertEqual(soxl.confidence, "LOW")
        self.assertEqual(soxl.trading_days, 252)
        self.assertTrue(soxl.promotion_eligible)
        self.assertFalse(soxl.demotion_eligible)

    def test_medium_confidence_promotion_requires_stronger_metrics(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("TQQQ", 50.0, 2.00, 25)])
            write_bars(root / "TQQQ.csv", 504)

            rows = build_confidence_report(
                scores_path,
                root,
                output_dir=root,
                starting_confidence={"TQQQ": "MEDIUM"},
            )

        tqqq = by_symbol(rows, "TQQQ")
        self.assertTrue(tqqq.promotion_eligible)
        self.assertFalse(tqqq.demotion_eligible)

    def test_high_confidence_demotes_on_weak_win_rate_or_profit_factor(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("TQQQ", 44.9, 2.00, 30)])
            write_bars(root / "TQQQ.csv", 600)

            rows = build_confidence_report(
                scores_path,
                root,
                output_dir=root,
                starting_confidence={"TQQQ": "HIGH"},
            )

        tqqq = by_symbol(rows, "TQQQ")
        self.assertFalse(tqqq.promotion_eligible)
        self.assertTrue(tqqq.demotion_eligible)

    def test_medium_confidence_demotes_to_low_on_weak_metrics(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("IONL", 36.0, 1.20, 20)])
            write_bars(root / "IONL.csv", 300)

            rows = build_confidence_report(
                scores_path,
                root,
                output_dir=root,
                starting_confidence={"IONL": "MEDIUM"},
            )

        ionl = by_symbol(rows, "IONL")
        self.assertFalse(ionl.promotion_eligible)
        self.assertTrue(ionl.demotion_eligible)

    def test_missing_metrics_are_not_promoted_or_demoted(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("SOXL", 60.0, 3.00, 30)])
            write_bars(root / "NEBX.csv", 197)

            rows = build_confidence_report(
                scores_path,
                root,
                output_dir=root,
                starting_confidence={"NEBX": "LOW"},
            )

        nebx = by_symbol(rows, "NEBX")
        self.assertIsNone(nebx.win_rate)
        self.assertIsNone(nebx.profit_factor)
        self.assertEqual(nebx.trade_count, 0)
        self.assertEqual(nebx.trading_days, 197)
        self.assertFalse(nebx.promotion_eligible)
        self.assertFalse(nebx.demotion_eligible)

    def test_current_metric_symbol_is_not_blocked_by_legacy_static_universe(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("NFLX", 58.82, 3.007, 34)])
            write_bars(root / "NFLX.csv", 600)

            rows = build_confidence_report(scores_path, root, output_dir=root)

        self.assertEqual([row.symbol for row in rows], ["NFLX"])
        nflx = by_symbol(rows, "NFLX")
        self.assertEqual(nflx.confidence, "LOW")
        self.assertTrue(nflx.promotion_eligible)

    def test_current_candidate_without_performance_stays_low_and_unpromoted(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("SOXL", 60.0, 3.00, 30)])

            rows = build_confidence_report(
                scores_path,
                root,
                output_dir=root,
                candidate_symbols=["NFLX"],
            )

        nflx = by_symbol(rows, "NFLX")
        self.assertEqual(nflx.confidence, "LOW")
        self.assertIsNone(nflx.win_rate)
        self.assertIsNone(nflx.profit_factor)
        self.assertEqual(nflx.trade_count, 0)
        self.assertFalse(nflx.promotion_eligible)
        self.assertFalse(nflx.demotion_eligible)

    def test_legacy_symbols_are_not_emitted_without_current_evidence_or_candidate_status(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("NFLX", 58.82, 3.007, 34)])

            rows = build_confidence_report(scores_path, root, output_dir=root)

        self.assertEqual({row.symbol for row in rows}, {"NFLX"})
        self.assertNotIn("NEBX", {row.symbol for row in rows})
        self.assertNotIn("TQQQ", {row.symbol for row in rows})

    def test_report_files_are_written(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("SOXL", 60.0, 3.00, 30)])
            write_bars(root / "SOXL.csv", 600)

            build_confidence_report(scores_path, root, output_dir=root)

            csv_text = (root / "confidence_report.csv").read_text(encoding="utf-8")
            payload = json.loads((root / "confidence_report.json").read_text(encoding="utf-8"))

        self.assertIn("symbol,confidence,win_rate,profit_factor,trade_count,trading_days", csv_text)
        self.assertTrue(payload["paper_trade_mode"])
        self.assertEqual(payload["universe_source"], "CURRENT_EVIDENCE_AND_CANDIDATES")
        self.assertFalse(payload["legacy_static_universe_enabled"])
        self.assertIn("promotion_rules", payload)
        self.assertIn("demotion_rules", payload)
        self.assertEqual(payload["rows"][0]["symbol"], "SOXL")

    def test_live_mode_is_rejected(self) -> None:
        with temp_data_dir() as directory:
            root = Path(directory)
            scores_path = root / "best_by_score.csv"
            write_scores(scores_path, [("SOXL", 60.0, 3.00, 30)])

            with self.assertRaises(ValueError):
                build_confidence_report(scores_path, root, paper_trade_mode=False)


def temp_data_dir() -> Iterator[str]:
    class TempDataDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"confidence_engine_test_{uuid.uuid4().hex}"

        def __enter__(self) -> str:
            self.path.mkdir()
            return str(self.path)

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for child in sorted(self.path.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                else:
                    child.rmdir()
            self.path.rmdir()

    return TempDataDir()


def by_symbol(rows: object, symbol: str) -> object:
    return {row.symbol: row for row in rows}[symbol]


def write_scores(path: Path, rows: list[tuple[str, float, float, int]]) -> None:
    lines = ["symbol,win_rate,profit_factor,number_of_trades"]
    lines.extend(f"{symbol},{win_rate},{profit_factor},{trades}" for symbol, win_rate, profit_factor, trades in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_bars(path: Path, rows: int) -> None:
    lines = ["date,open,high,low,close,volume"]
    for index in range(rows):
        lines.append(f"2025-01-01,10,11,9,10,1000")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

import json
import unittest
import uuid
from collections.abc import Iterator
from pathlib import Path

from swing_trade_bot.allocation_engine import (
    allocate_weights,
    allocate_weights_with_caps,
    build_allocation_report,
    read_scores,
)


class AllocationEngineTests(unittest.TestCase):
    def test_scores_are_normalized_to_allocations(self) -> None:
        with temp_data_dir() as directory:
            scores_path = Path(directory) / "best_by_score.csv"
            write_scores(scores_path, [("SOXL", 2.0), ("TQQQ", 1.0), ("IONL", 1.0)])

            rows = build_allocation_report(
                scores_path,
                monthly_contribution=1000.0,
                confidence_overrides={"IONL": "HIGH"},
            )

        self.assertEqual([row.symbol for row in rows], ["SOXL", "TQQQ", "IONL"])
        self.assertAlmostEqual(sum(row.weight for row in rows), 1.0)
        self.assertEqual(rows[0].allocation_amount, 350.0)
        self.assertEqual(rows[1].allocation_amount, 325.0)
        self.assertEqual(rows[2].allocation_amount, 325.0)

    def test_minimum_floor_and_maximum_cap_are_applied(self) -> None:
        weights = allocate_weights([100.0, 1.0, 1.0, 1.0])

        self.assertAlmostEqual(sum(weights), 1.0)
        self.assertEqual(weights[0], 0.35)
        self.assertTrue(all(weight >= 0.05 for weight in weights))
        self.assertTrue(all(weight <= 0.35 for weight in weights))

    def test_confidence_adjustment_and_caps_are_applied(self) -> None:
        with temp_data_dir() as directory:
            scores_path = Path(directory) / "best_by_score.csv"
            write_scores(scores_path, [("AAA", 1.0), ("BBB", 1.0), ("CCC", 1.0)])

            rows = build_allocation_report(
                scores_path,
                monthly_contribution=1000.0,
                confidence_overrides={"BBB": "LOW"},
            )

        self.assertAlmostEqual(sum(row.weight for row in rows), 0.75)
        self.assertEqual(rows[0].weight, 0.35)
        self.assertAlmostEqual(rows[1].weight, 0.05)
        self.assertEqual(rows[2].weight, 0.35)
        self.assertEqual(rows[1].confidence, "LOW")
        self.assertEqual(rows[1].adjusted_score, 0.5)

    def test_medium_confidence_is_capped_at_ten_percent(self) -> None:
        with temp_data_dir() as directory:
            scores_path = Path(directory) / "best_by_score.csv"
            write_scores(scores_path, [("AAA", 1.0), ("BBB", 10.0), ("CCC", 1.0)])

            rows = build_allocation_report(
                scores_path,
                monthly_contribution=1000.0,
                confidence_overrides={"BBB": "MEDIUM"},
            )

        by_symbol = {row.symbol: row for row in rows}
        self.assertEqual(by_symbol["BBB"].weight, 0.10)
        self.assertEqual(by_symbol["BBB"].allocation_amount, 100.0)

    def test_report_files_are_written(self) -> None:
        with temp_data_dir() as directory:
            output_dir = Path(directory) / "reports"
            scores_path = Path(directory) / "best_by_score.csv"
            write_scores(scores_path, [("SOXL", 1.0), ("TQQQ", 1.0), ("IONL", 1.0)])

            build_allocation_report(
                scores_path,
                monthly_contribution=1000.0,
                output_dir=output_dir,
            )

            csv_text = (output_dir / "allocation_report.csv").read_text(encoding="utf-8")
            payload = json.loads((output_dir / "allocation_report.json").read_text(encoding="utf-8"))

        self.assertIn("symbol,score,confidence,bucket,adjusted_score,weight,allocation_amount", csv_text)
        self.assertTrue(payload["paper_trade_mode"])
        self.assertEqual(payload["monthly_contribution"], 1000.0)
        self.assertEqual(len(payload["allocations"]), 3)
        self.assertIn("unallocated_amount", payload)

    def test_dca_universe_adds_emerging_symbols_with_starter_scores(self) -> None:
        with temp_data_dir() as directory:
            scores_path = Path(directory) / "best_by_score.csv"
            write_scores(scores_path, [("SOXL", 0.8), ("TQQQ", 0.7), ("IONL", 0.6)])

            rows = build_allocation_report(
                scores_path,
                monthly_contribution=1000.0,
                include_dca_universe=True,
            )

        by_symbol = {row.symbol: row for row in rows}
        self.assertEqual([row.symbol for row in rows], ["SOXL", "TQQQ", "IONL", "BEX", "IRE", "DRAM", "NEBX"])
        self.assertEqual(by_symbol["SOXL"].confidence, "HIGH")
        self.assertEqual(by_symbol["TQQQ"].confidence, "HIGH")
        self.assertEqual(by_symbol["IONL"].confidence, "LOW")
        self.assertEqual(by_symbol["NEBX"].confidence, "LOW")
        self.assertEqual(by_symbol["NEBX"].score, 0.25)
        self.assertEqual(by_symbol["NEBX"].bucket, "EMERGING")
        self.assertAlmostEqual(sum(row.weight for row in rows), 0.95)

    def test_per_symbol_caps_can_leave_cash_unallocated(self) -> None:
        weights = allocate_weights_with_caps(
            [1.0, 1.0, 1.0],
            maximums=[0.35, 0.10, 0.05],
        )

        self.assertEqual(weights, [0.35, 0.10, 0.05])
        self.assertAlmostEqual(sum(weights), 0.50)

    def test_invalid_confidence_is_rejected(self) -> None:
        with temp_data_dir() as directory:
            scores_path = Path(directory) / "best_by_score.csv"
            scores_path.write_text("symbol,score,confidence\nAAA,1.0,BAD\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                read_scores(scores_path)

    def test_live_mode_is_rejected(self) -> None:
        with temp_data_dir() as directory:
            scores_path = Path(directory) / "best_by_score.csv"
            write_scores(scores_path, [("SOXL", 1.0)])

            with self.assertRaises(ValueError):
                build_allocation_report(
                    scores_path,
                    monthly_contribution=1000.0,
                    paper_trade_mode=False,
                )


def temp_data_dir() -> Iterator[str]:
    class TempDataDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"allocation_engine_test_{uuid.uuid4().hex}"

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


def write_scores(path: Path, rows: list[tuple[str, float]]) -> None:
    lines = ["symbol,score"]
    lines.extend(f"{symbol},{score}" for symbol, score in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

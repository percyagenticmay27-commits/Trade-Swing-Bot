import csv
import json
import unittest
import uuid
from pathlib import Path

from swing_trade_bot.opportunity_quality_engine import (
    COMPONENT_WEIGHTS,
    OpportunityQualityEngine,
    OpportunityQualityInput,
    build_opportunity_quality_report,
    format_opportunity_quality_markdown,
    write_opportunity_quality_reports,
)


class OpportunityQualityEngineTests(unittest.TestCase):
    def test_version_1_2_weights_are_frozen(self) -> None:
        self.assertEqual(
            COMPONENT_WEIGHTS,
            {
                "fundamental_analysis_score": 0.20,
                "market_intelligence_score": 0.20,
                "conviction_score": 0.20,
                "momentum_score": 0.15,
                "technical_analysis_score": 0.15,
                "market_regime_support_score": 0.05,
                "portfolio_risk_adjustment_score": 0.05,
            },
        )
        self.assertAlmostEqual(sum(COMPONENT_WEIGHTS.values()), 1.0)

    def test_missing_evidence_is_zero(self) -> None:
        report = OpportunityQualityEngine().evaluate([OpportunityQualityInput(symbol="SOXL")])
        row = report.rows[0]

        self.assertEqual(row.opportunity_quality_score, 0.0)
        self.assertEqual(row.opportunity_quality_level, "WATCHLIST")
        self.assertEqual(row.entry_score, 0.0)

    def test_entry_score_is_display_only(self) -> None:
        low_entry = OpportunityQualityInput(
            symbol="SOXL",
            fundamental_analysis_score=80,
            market_intelligence_score=80,
            conviction_score=80,
            momentum_score=80,
            technical_analysis_score=80,
            market_regime_support_score=80,
            portfolio_risk_adjustment_score=80,
            entry_score=0,
        )
        high_entry = OpportunityQualityInput(
            symbol="SOXL",
            fundamental_analysis_score=80,
            market_intelligence_score=80,
            conviction_score=80,
            momentum_score=80,
            technical_analysis_score=80,
            market_regime_support_score=80,
            portfolio_risk_adjustment_score=80,
            entry_score=100,
        )
        rows = OpportunityQualityEngine().evaluate([low_entry, high_entry]).rows

        self.assertEqual(rows[0].opportunity_quality_score, rows[1].opportunity_quality_score)
        self.assertFalse(rows[0].entry_score_gate_passed)
        self.assertTrue(rows[1].entry_score_gate_passed)

    def test_live_and_qa_modes_use_identical_calculations(self) -> None:
        opportunity = OpportunityQualityInput(
            symbol="TQQQ",
            fundamental_analysis_score=90,
            market_intelligence_score=80,
            conviction_score=70,
            momentum_score=60,
            technical_analysis_score=50,
            market_regime_support_score=40,
            portfolio_risk_adjustment_score=30,
        )

        qa = OpportunityQualityEngine(system_mode="QA").evaluate([opportunity]).rows[0]
        live = OpportunityQualityEngine(system_mode="LIVE").evaluate([opportunity]).rows[0]

        self.assertEqual(qa.opportunity_quality_score, live.opportunity_quality_score)
        self.assertEqual(qa.system_mode, "QA")
        self.assertEqual(live.system_mode, "LIVE")

    def test_report_files_are_written(self) -> None:
        with temp_dir() as directory:
            report = OpportunityQualityEngine().evaluate([
                OpportunityQualityInput(symbol="SOXL", fundamental_analysis_score=100, market_intelligence_score=100)
            ])
            csv_path, json_path, md_path = write_opportunity_quality_reports(directory, report)
            csv_rows = list(csv.DictReader(csv_path.open(newline="", encoding="utf-8")))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")

        self.assertEqual(csv_rows[0]["symbol"], "SOXL")
        self.assertTrue(payload["paper_trade_mode"])
        self.assertTrue(payload["entry_score_display_only"])
        self.assertIn("Opportunity Quality Report", markdown)

    def test_build_report_from_csv(self) -> None:
        with temp_dir() as directory:
            input_path = directory / "quality.csv"
            input_path.write_text(
                "symbol,fundamental_analysis_score,market_intelligence_score,conviction_score,momentum_score,technical_analysis_score,market_regime_support_score,portfolio_risk_adjustment_score,entry_score\n"
                "SOXL,100,90,80,70,60,50,40,30\n",
                encoding="utf-8",
            )
            report = build_opportunity_quality_report(input_path=input_path, output_dir=directory)

        self.assertEqual(report.rows[0].symbol, "SOXL")
        self.assertGreater(report.rows[0].opportunity_quality_score, 0.0)

    def test_markdown_mentions_entry_score_display_only(self) -> None:
        report = OpportunityQualityEngine().evaluate([OpportunityQualityInput(symbol="SOXL", entry_score=80)])

        self.assertIn("display-only", format_opportunity_quality_markdown(report))

    def test_live_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OpportunityQualityEngine(paper_trade_mode=False)


def temp_dir():
    class TempDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"opportunity_quality_test_{uuid.uuid4().hex}"

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

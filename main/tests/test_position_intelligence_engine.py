import json
import tempfile
import unittest
from pathlib import Path

from swing_trade_bot.position_intelligence_engine import (
    DECISION_STATES,
    PAPER_TRADE_MODE,
    PositionIntelligenceReport,
    build_and_write_position_intelligence_report,
    build_position_intelligence_report,
    format_console_summary,
    format_position_intelligence_markdown,
    write_position_intelligence_reports,
)


class PositionIntelligenceEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.results_dir = self.root / "results"
        self.data_dir = self.root / "data"
        self.results_dir.mkdir()
        self.data_dir.mkdir()
        self._write_required_reports()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_required_reports(self) -> None:
        self._write_json(
            self.results_dir / "opportunity_quality.json",
            {
                "paper_trade_mode": True,
                "symbol_opportunity_quality": [
                    {
                        "symbol": "AMDL",
                        "opportunity_quality_score": 92,
                        "opportunity_classification": "HIGH_OPPORTUNITY",
                        "entry_gate_status": "ENTRY_FAVORABLE",
                        "lifecycle_state": "WATCHLIST",
                        "final_opportunity_status": "HIGH_QUALITY_ENTRY_READY",
                    },
                    {
                        "symbol": "SOXL",
                        "opportunity_quality_score": 88,
                        "opportunity_classification": "HIGH_OPPORTUNITY",
                        "entry_gate_status": "ENTRY_BLOCKED",
                        "lifecycle_state": "WATCHLIST",
                        "final_opportunity_status": "HIGH_QUALITY_WAIT_FOR_ENTRY",
                    },
                    {
                        "symbol": "TQQQ",
                        "opportunity_quality_score": 89,
                        "opportunity_classification": "HIGH_OPPORTUNITY",
                        "entry_gate_status": "ENTRY_FAVORABLE",
                        "lifecycle_state": "REENTRY_CANDIDATE",
                        "final_opportunity_status": "HIGH_QUALITY_REENTRY_READY",
                    },
                    {
                        "symbol": "BEX",
                        "opportunity_quality_score": 44,
                        "opportunity_classification": "LOW_OPPORTUNITY",
                        "entry_gate_status": "ENTRY_NEUTRAL",
                        "lifecycle_state": "ACTIVE_POSITION",
                        "final_opportunity_status": "ACTIVE_POSITION",
                    },
                    {
                        "symbol": "NEBX",
                        "opportunity_quality_score": 35,
                        "opportunity_classification": "LOW_OPPORTUNITY",
                        "entry_gate_status": "UNKNOWN",
                        "lifecycle_state": "EXIT_REVIEW",
                        "final_opportunity_status": "EXIT_REVIEW",
                    },
                    {
                        "symbol": "IONL",
                        "opportunity_quality_score": 86,
                        "opportunity_classification": "HIGH_OPPORTUNITY",
                        "entry_gate_status": "ENTRY_NEUTRAL",
                        "lifecycle_state": "REENTRY_WATCH",
                        "final_opportunity_status": "HIGH_QUALITY_REENTRY_WAIT",
                    },
                    {
                        "symbol": "DRAM",
                        "opportunity_quality_score": 20,
                        "opportunity_classification": "AVOID_FOR_NOW",
                        "entry_gate_status": "ENTRY_BLOCKED",
                        "lifecycle_state": "WATCHLIST",
                        "final_opportunity_status": "AVOID_FOR_NOW",
                    },
                ],
            },
        )
        self._write_json(
            self.results_dir / "strategy_assignments.json",
            {
                "paper_trade_mode": True,
                "assignments": [
                    {"symbol": "AMDL", "assigned_strategy": "Strategy A"},
                    {"symbol": "SOXL", "assigned_strategy": "Strategy B"},
                    {"symbol": "TQQQ", "assigned_strategy": "Strategy B"},
                    {"symbol": "BEX", "assigned_strategy": "Strategy A"},
                    {"symbol": "NEBX", "assigned_strategy": "Strategy B"},
                    {"symbol": "IONL", "assigned_strategy": "Strategy B"},
                    {"symbol": "DRAM", "assigned_strategy": "Strategy A"},
                ],
            },
        )
        self._write_json(
            self.results_dir / "trade_lifecycle_report.json",
            {
                "paper_trade_mode": True,
                "reviews": [
                    {"symbol": "BEX", "recommended_state": "paper_position", "suggested_action": "continue_research_position"},
                    {"symbol": "NEBX", "recommended_state": "review_required", "suggested_action": "review_thesis"},
                    {"symbol": "IONL", "recommended_state": "reentry_watch", "suggested_action": "research_reentry"},
                ],
            },
        )
        self._write_json(
            self.results_dir / "profit_protection_report.json",
            {
                "paper_trade_mode": True,
                "reviews": [
                    {"symbol": "BEX", "suggested_review_action": "monitor", "protection_zone": "below_protection_zone"}
                ],
            },
        )
        self._write_json(
            self.results_dir / "reentry_report.json",
            {
                "paper_trade_mode": True,
                "reviews": [
                    {"symbol": "TQQQ", "reentry_state": "ready", "suggested_review_action": "prepare_reentry_review"}
                ],
            },
        )
        self._write_json(
            self.results_dir / "exit_review_report.json",
            {
                "paper_trade_mode": True,
                "reviews": [
                    {"symbol": "NEBX", "outcome": "review_exit", "suggested_review_action": "review_exit"}
                ],
            },
        )
        self._write_json(
            self.results_dir / "portfolio_allocations.json",
            {
                "paper_trade_mode": True,
                "allocations": [
                    {"symbol": "BEX", "allocation_pct": 15},
                    {"symbol": "SGOV", "allocation_pct": 30},
                ],
            },
        )

    def _state_for(self, report, symbol: str) -> str:
        for row in report.symbol_position_intelligence:
            if row.symbol == symbol:
                return row.decision_state
        raise AssertionError(f"Missing symbol {symbol}")

    def test_paper_trade_mode_enforced(self) -> None:
        self.assertTrue(PAPER_TRADE_MODE)
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertTrue(report.paper_trade_mode)
        self.assertTrue(report.summary_metrics.paper_trade_mode)

    def test_required_inputs_missing_raise_error(self) -> None:
        (self.results_dir / "opportunity_quality.json").unlink()
        with self.assertRaises(FileNotFoundError):
            build_position_intelligence_report(str(self.results_dir), str(self.data_dir))

    def test_optional_inputs_missing_create_warnings(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertGreater(report.summary_metrics.warning_count, 0)
        self.assertTrue(any(w.severity == "low" for w in report.warnings))

    def test_json_output_generation(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        write_position_intelligence_reports(str(self.results_dir), report)
        self.assertTrue((self.results_dir / "position_intelligence.json").exists())
        payload = json.loads((self.results_dir / "position_intelligence.json").read_text(encoding="utf-8"))
        self.assertTrue(payload["paper_trade_mode"])

    def test_markdown_output_generation(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        write_position_intelligence_reports(str(self.results_dir), report)
        markdown = (self.results_dir / "position_intelligence.md").read_text(encoding="utf-8")
        self.assertIn("# Position Intelligence Report", markdown)
        self.assertIn("## Daily Decision Summary", markdown)

    def test_report_metadata(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertIsInstance(report, PositionIntelligenceReport)
        self.assertEqual(report.report_version, "1.3")
        self.assertEqual(report.generated_by, "position_intelligence_engine")
        self.assertTrue(report.generated_at_utc)

    def test_data_source_status(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(report.data_sources["required"]["opportunity_quality"], "loaded")
        self.assertEqual(report.data_sources["optional"]["executive_dashboard"], "missing")

    def test_summary_metrics(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertGreaterEqual(report.summary_metrics.symbols_analyzed, 7)
        self.assertGreaterEqual(report.summary_metrics.strategy_b_count, 3)
        self.assertEqual(report.summary_metrics.review_action_count, len(report.suggested_review_actions))

    def test_decision_states_are_allowed(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        for row in report.symbol_position_intelligence:
            self.assertIn(row.decision_state, DECISION_STATES)

    def test_review_entry_state(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(self._state_for(report, "AMDL"), "REVIEW_ENTRY")

    def test_review_reentry_state(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(self._state_for(report, "TQQQ"), "REVIEW_REENTRY")

    def test_hold_active_position_state(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(self._state_for(report, "BEX"), "HOLD_ACTIVE_POSITION")

    def test_review_exit_state(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(self._state_for(report, "NEBX"), "REVIEW_EXIT")

    def test_wait_for_entry_state(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(self._state_for(report, "SOXL"), "WAIT_FOR_ENTRY")

    def test_wait_for_reentry_state(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(self._state_for(report, "IONL"), "WAIT_FOR_REENTRY")

    def test_remove_from_active_review_state(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(self._state_for(report, "DRAM"), "REMOVE_FROM_ACTIVE_REVIEW")

    def test_profit_protection_priority(self) -> None:
        self._write_json(
            self.results_dir / "profit_protection_report.json",
            {"paper_trade_mode": True, "reviews": [{"symbol": "BEX", "suggested_review_action": "standard_profit_review", "protection_zone": "standard_protection_zone"}]},
        )
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(self._state_for(report, "BEX"), "REVIEW_PROFIT_PROTECTION")

    def test_exit_review_priority(self) -> None:
        self._write_json(
            self.results_dir / "profit_protection_report.json",
            {"paper_trade_mode": True, "reviews": [{"symbol": "NEBX", "suggested_review_action": "standard_profit_review", "protection_zone": "standard_protection_zone"}]},
        )
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertEqual(self._state_for(report, "NEBX"), "REVIEW_EXIT")

    def test_strategy_a_and_b_handling(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        rows = {row.symbol: row.strategy_assignment for row in report.symbol_position_intelligence}
        self.assertEqual(rows["AMDL"], "Strategy A")
        self.assertEqual(rows["SOXL"], "Strategy B")

    def test_strategy_b_capital_preservation_flag(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertTrue(any(f.flag_type == "strategy_b_capital_preservation" for f in report.risk_flags))

    def test_reentry_requires_high_opportunity_quality_context(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        row = next(row for row in report.symbol_position_intelligence if row.symbol == "TQQQ")
        self.assertIn(row.opportunity_classification, {"HIGH_OPPORTUNITY", "ELITE_OPPORTUNITY"})
        self.assertEqual(row.decision_state, "REVIEW_REENTRY")

    def test_entry_gate_is_not_overridden(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        row = next(row for row in report.symbol_position_intelligence if row.symbol == "SOXL")
        self.assertEqual(row.entry_gate_status, "ENTRY_BLOCKED")
        self.assertEqual(row.decision_state, "WAIT_FOR_ENTRY")

    def test_risk_flags_generated(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertTrue(report.risk_flags)
        self.assertTrue(any(flag.flag_type == "exit_review_required" for flag in report.risk_flags))

    def test_suggested_review_actions_generated(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertTrue(report.suggested_review_actions)
        self.assertTrue(any(action.action_type == "REVIEW_EXIT" for action in report.suggested_review_actions))

    def test_suggested_review_actions_sorted_by_priority(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        priorities = [order[action.priority] for action in report.suggested_review_actions]
        self.assertEqual(priorities, sorted(priorities))

    def test_console_summary(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        summary = format_console_summary(report)
        self.assertIn("Position Intelligence", summary)
        self.assertIn("symbols=", summary)

    def test_build_write_build_and_write_workflow(self) -> None:
        report = build_and_write_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertIsInstance(report, PositionIntelligenceReport)
        self.assertTrue((self.results_dir / "position_intelligence.json").exists())
        self.assertTrue((self.results_dir / "position_intelligence.md").exists())

    def test_malformed_required_json_raises_clear_error(self) -> None:
        (self.results_dir / "opportunity_quality.json").write_text("{bad json", encoding="utf-8")
        with self.assertRaises(ValueError):
            build_position_intelligence_report(str(self.results_dir), str(self.data_dir))

    def test_malformed_optional_json_creates_warning(self) -> None:
        (self.results_dir / "executive_dashboard.json").write_text("{bad json", encoding="utf-8")
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertTrue(any(w.source == "executive_dashboard.json" and w.severity == "medium" for w in report.warnings))

    def test_malformed_optional_csv_creates_warning(self) -> None:
        (self.results_dir / "confidence_report.csv").write_text("\x00", encoding="utf-8")
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        self.assertTrue(any(w.source == "confidence_report.csv" and w.severity == "medium" for w in report.warnings))

    def test_no_robinhood_execution(self) -> None:
        source = Path("src/swing_trade_bot/position_intelligence_engine.py")
        if source.exists():
            text = source.read_text(encoding="utf-8").lower()
            self.assertNotIn("robinhood", text.replace("no robinhood", ""))

    def test_no_broker_execution(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        rendered = json.dumps(json.loads(json.dumps(report, default=lambda o: getattr(o, "__dict__", str(o))))).lower()
        self.assertNotIn("broker integration enabled", rendered)

    def test_no_order_fields(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        payload = json.loads(json.dumps(report, default=lambda o: getattr(o, "__dict__", str(o))))
        text = json.dumps(payload).lower()
        self.assertNotIn("order_id", text)
        self.assertNotIn("market_order", text)

    def test_no_buy_sell_execute_language(self) -> None:
        report = build_position_intelligence_report(str(self.results_dir), str(self.data_dir))
        for action in report.suggested_review_actions:
            text = f"{action.action_type} {action.message}".lower()
            self.assertNotIn("buy", text)
            self.assertNotIn("sell", text)
            self.assertNotIn("execute", text)
            self.assertNotIn("trade now", text)

    def test_no_live_market_news_price_fetching(self) -> None:
        markdown = format_position_intelligence_markdown(build_position_intelligence_report(str(self.results_dir), str(self.data_dir)))
        self.assertIn("No live market/news/price fetching", markdown)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from swing_trade_bot.swing_cio_plugin_manifest import (
    IMMUTABLE_SAFETY_VALUES,
    build_manifest_summary,
    load_plugin_manifest,
    validate_plugin_manifest,
)


class SwingCioPluginManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository_root = Path(__file__).resolve().parents[1]
        cls.manifest_path = cls.repository_root / "configs" / "swing_cio_plugin_manifest.json"
        cls.manifest = load_plugin_manifest(cls.manifest_path)

    def test_manifest_file_is_valid_json_object(self) -> None:
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertIsInstance(payload, dict)

    def test_current_manifest_validates(self) -> None:
        result = validate_plugin_manifest(self.manifest)
        self.assertTrue(result.valid, result.errors)
        self.assertEqual((), result.errors)

    def test_plugin_identity_is_stable(self) -> None:
        self.assertEqual("SWING-001", self.manifest["plugin_id"])
        self.assertEqual("Trade-Swing-Bot", self.manifest["repository_name"])
        self.assertEqual("STRATEGY_PLUGIN", self.manifest["plugin_type"])
        self.assertEqual("SWING_TRADING", self.manifest["strategy_class"])

    def test_all_capabilities_are_advisory_only(self) -> None:
        capabilities = self.manifest["capabilities"]
        self.assertGreater(len(capabilities), 0)
        self.assertTrue(all(item["advisory_only"] is True for item in capabilities))

    def test_capability_ids_are_unique(self) -> None:
        ids = [item["capability_id"] for item in self.manifest["capabilities"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_report_ids_are_unique(self) -> None:
        ids = [item["report_id"] for item in self.manifest["published_reports"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_report_has_owner_artifacts_and_destination(self) -> None:
        for report in self.manifest["published_reports"]:
            self.assertTrue(report["owner_module"])
            self.assertTrue(report["artifacts"])
            self.assertTrue(report["dashboard_destination"])

    def test_immutable_safety_flags_match(self) -> None:
        safety = self.manifest["safety"]
        for key, expected in IMMUTABLE_SAFETY_VALUES.items():
            self.assertIs(safety[key], expected)

    def test_live_trading_cannot_be_enabled(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["safety"]["live_trading_enabled"] = True
        result = validate_plugin_manifest(changed)
        self.assertFalse(result.valid)
        self.assertIn("Safety flag live_trading_enabled must be False", result.errors)

    def test_paper_trade_mode_cannot_be_disabled(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["safety"]["paper_trade_mode"] = False
        result = validate_plugin_manifest(changed)
        self.assertFalse(result.valid)
        self.assertIn("Safety flag paper_trade_mode must be True", result.errors)

    def test_direct_database_writes_cannot_be_enabled(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["compatibility"]["direct_database_writes"] = True
        result = validate_plugin_manifest(changed)
        self.assertFalse(result.valid)
        self.assertIn("direct_database_writes must be false", result.errors)

    def test_duplicate_capability_is_rejected(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["capabilities"].append(copy.deepcopy(changed["capabilities"][0]))
        result = validate_plugin_manifest(changed)
        self.assertFalse(result.valid)
        self.assertTrue(any(error.startswith("Duplicate capability_id") for error in result.errors))

    def test_duplicate_report_is_rejected(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["published_reports"].append(copy.deepcopy(changed["published_reports"][0]))
        result = validate_plugin_manifest(changed)
        self.assertFalse(result.valid)
        self.assertTrue(any(error.startswith("Duplicate report_id") for error in result.errors))

    def test_unsupported_artifact_format_is_rejected(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["published_reports"][0]["artifacts"].append("results/not_allowed.exe")
        result = validate_plugin_manifest(changed)
        self.assertFalse(result.valid)
        self.assertIn("Unsupported artifact format: results/not_allowed.exe", result.errors)

    def test_missing_optional_artifact_is_warning_not_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = validate_plugin_manifest(self.manifest, repository_root=directory)
        self.assertTrue(result.valid, result.errors)
        self.assertGreater(len(result.warnings), 0)

    def test_missing_required_artifact_is_error(self) -> None:
        changed = copy.deepcopy(self.manifest)
        changed["published_reports"][0]["required"] = True
        with tempfile.TemporaryDirectory() as directory:
            result = validate_plugin_manifest(changed, repository_root=directory)
        self.assertFalse(result.valid)
        self.assertTrue(any(error.startswith("Artifact not currently present") for error in result.errors))

    def test_summary_contains_registration_and_safety(self) -> None:
        summary = build_manifest_summary(self.manifest)
        self.assertEqual("SWING-001", summary["plugin_id"])
        self.assertEqual("CIO_DISCOVERABLE", summary["registration_status"])
        self.assertIs(summary["paper_trade_mode"], True)
        self.assertIs(summary["advisory_only"], True)
        self.assertIs(summary["live_trading_enabled"], False)
        self.assertGreater(summary["capability_count"], 0)

    def test_load_missing_manifest_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "Plugin manifest not found"):
            load_plugin_manifest(self.repository_root / "configs" / "missing.json")

    def test_load_non_object_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "root must be a JSON object"):
                load_plugin_manifest(path)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from swing_trade_bot.swing_cio_presentation_adapter import (
    build_presentation,
    format_presentation_markdown,
    load_adapter_config,
    validate_adapter_config,
    write_presentation_outputs,
)


class SwingCioPresentationAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "adapter_schema_version": "1.0",
            "adapter_id": "TEST-ADAPTER",
            "plugin_id": "SWING-001",
            "adapter_version": "1.0.0",
            "paper_trade_mode": True,
            "advisory_only": True,
            "read_only_sources": True,
            "direct_database_writes": False,
            "outputs": {"json": "results/out.json", "markdown": "results/out.md"},
            "presentations": [
                {
                    "presentation_id": "strategy",
                    "artifact_id": "strategy_assignments_json",
                    "artifact_version": "1.3",
                    "source_path": "results/strategy_assignments.json",
                    "required": False,
                    "dashboard_destination": "Strategy Assignment",
                    "title": "Strategy Assignment",
                    "record_path": "assignments",
                    "key_fields": ["symbol", "recommended_strategy"],
                }
            ],
        }
        self.registry = {
            "registrations": [
                {"artifact_id": "strategy_assignments_json", "artifact_version": "1.3"}
            ]
        }

    def test_valid_config_passes(self) -> None:
        self.assertTrue(validate_adapter_config(self.config).valid)

    def test_missing_required_top_level_field_is_rejected(self) -> None:
        value = copy.deepcopy(self.config)
        del value["adapter_id"]
        self.assertFalse(validate_adapter_config(value).valid)

    def test_schema_version_is_locked(self) -> None:
        value = copy.deepcopy(self.config)
        value["adapter_schema_version"] = "2.0"
        self.assertFalse(validate_adapter_config(value).valid)

    def test_paper_trade_mode_is_locked(self) -> None:
        value = copy.deepcopy(self.config)
        value["paper_trade_mode"] = False
        self.assertFalse(validate_adapter_config(value).valid)

    def test_advisory_only_is_locked(self) -> None:
        value = copy.deepcopy(self.config)
        value["advisory_only"] = False
        self.assertFalse(validate_adapter_config(value).valid)

    def test_read_only_sources_is_locked(self) -> None:
        value = copy.deepcopy(self.config)
        value["read_only_sources"] = False
        self.assertFalse(validate_adapter_config(value).valid)

    def test_direct_database_writes_are_rejected(self) -> None:
        value = copy.deepcopy(self.config)
        value["direct_database_writes"] = True
        self.assertFalse(validate_adapter_config(value).valid)

    def test_output_json_extension_is_validated(self) -> None:
        value = copy.deepcopy(self.config)
        value["outputs"]["json"] = "out.txt"
        self.assertFalse(validate_adapter_config(value).valid)

    def test_output_markdown_extension_is_validated(self) -> None:
        value = copy.deepcopy(self.config)
        value["outputs"]["markdown"] = "out.txt"
        self.assertFalse(validate_adapter_config(value).valid)

    def test_duplicate_presentation_id_is_rejected(self) -> None:
        value = copy.deepcopy(self.config)
        value["presentations"].append(copy.deepcopy(value["presentations"][0]))
        self.assertFalse(validate_adapter_config(value).valid)

    def test_duplicate_artifact_version_is_rejected(self) -> None:
        value = copy.deepcopy(self.config)
        duplicate = copy.deepcopy(value["presentations"][0])
        duplicate["presentation_id"] = "different"
        value["presentations"].append(duplicate)
        self.assertFalse(validate_adapter_config(value).valid)

    def test_duplicate_key_fields_are_rejected(self) -> None:
        value = copy.deepcopy(self.config)
        value["presentations"][0]["key_fields"] = ["symbol", "symbol"]
        self.assertFalse(validate_adapter_config(value).valid)

    def test_invalid_record_path_is_rejected(self) -> None:
        value = copy.deepcopy(self.config)
        value["presentations"][0]["record_path"] = 3
        self.assertFalse(validate_adapter_config(value).valid)

    def test_required_must_be_boolean(self) -> None:
        value = copy.deepcopy(self.config)
        value["presentations"][0]["required"] = "false"
        self.assertFalse(validate_adapter_config(value).valid)

    def test_missing_optional_artifact_creates_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = build_presentation(self.config, temp, registry=self.registry)
        self.assertEqual(result["status"], "READY_WITH_WARNINGS")
        self.assertEqual(result["available_section_count"], 0)

    def test_missing_required_artifact_creates_error(self) -> None:
        value = copy.deepcopy(self.config)
        value["presentations"][0]["required"] = True
        with tempfile.TemporaryDirectory() as temp:
            result = build_presentation(value, temp, registry=self.registry)
        self.assertEqual(result["status"], "ERROR")

    def test_unregistered_optional_artifact_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = build_presentation(self.config, temp, registry={"registrations": []})
        self.assertEqual(result["sections"][0]["status"], "UNAVAILABLE")

    def test_unregistered_required_artifact_is_error(self) -> None:
        value = copy.deepcopy(self.config)
        value["presentations"][0]["required"] = True
        with tempfile.TemporaryDirectory() as temp:
            result = build_presentation(value, temp, registry={"registrations": []})
        self.assertEqual(result["sections"][0]["status"], "ERROR")

    def test_available_artifact_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "results" / "strategy_assignments.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"version": "1.3", "assignments": [{"symbol": "AMD", "recommended_strategy": "Strategy A", "ignored": 5}]}), encoding="utf-8")
            result = build_presentation(self.config, temp, registry=self.registry)
        section = result["sections"][0]
        self.assertEqual(section["status"], "AVAILABLE")
        self.assertEqual(section["records"], [{"symbol": "AMD", "recommended_strategy": "Strategy A"}])

    def test_source_files_are_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "results" / "strategy_assignments.json"
            path.parent.mkdir(parents=True)
            original = json.dumps({"assignments": []})
            path.write_text(original, encoding="utf-8")
            result = build_presentation(self.config, temp, registry=self.registry)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertFalse(result["source_files_modified"])

    def test_invalid_json_is_reported_without_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "results" / "strategy_assignments.json"
            path.parent.mkdir(parents=True)
            path.write_text("{bad", encoding="utf-8")
            result = build_presentation(self.config, temp, registry=self.registry)
        self.assertEqual(result["sections"][0]["status"], "UNAVAILABLE")

    def test_non_list_record_path_creates_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "results" / "strategy_assignments.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"assignments": {}}), encoding="utf-8")
            result = build_presentation(self.config, temp, registry=self.registry)
        self.assertTrue(result["sections"][0]["warnings"])

    def test_markdown_contains_title_and_status(self) -> None:
        presentation = {
            "status": "READY",
            "generated_at_utc": "2026-01-01T00:00:00Z",
            "available_section_count": 1,
            "section_count": 1,
            "sections": [{
                "title": "Strategy Assignment",
                "status": "AVAILABLE",
                "artifact_id": "a",
                "artifact_version": "1.0",
                "dashboard_destination": "D",
                "record_count": 0,
                "warnings": [],
                "records": [],
            }],
        }
        text = format_presentation_markdown(presentation)
        self.assertIn("# Swing CIO Presentation", text)
        self.assertIn("Strategy Assignment", text)

    def test_write_outputs_creates_json_and_markdown(self) -> None:
        presentation = {"status": "READY", "sections": [], "available_section_count": 0, "section_count": 0}
        with tempfile.TemporaryDirectory() as temp:
            json_path, markdown_path = write_presentation_outputs(temp, presentation)
            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())

    def test_load_config_rejects_non_object_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_adapter_config(path)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from swing_trade_bot.swing_schema_registry import (
    build_registry_summary,
    get_latest_active_registration,
    get_schema_registration,
    is_schema_compatible,
    list_artifact_versions,
    load_schema_registry,
    validate_schema_registry,
)


class SwingSchemaRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = Path(__file__).parents[1] / "configs" / "swing_cio_schema_registry.json"
        cls.registry = load_schema_registry(cls.path)

    def test_registry_loads(self):
        self.assertIsInstance(self.registry, dict)

    def test_registry_is_valid(self):
        self.assertTrue(validate_schema_registry(self.registry).valid)

    def test_registry_identity(self):
        self.assertEqual(self.registry["registry_id"], "SWING-CIO-SCHEMA-REGISTRY")
        self.assertEqual(self.registry["plugin_id"], "SWING-001")

    def test_strict_versioning_is_locked(self):
        self.assertEqual(self.registry["versioning_policy"], "STRICT_ARTIFACT_VERSIONING")

    def test_paper_trade_mode_is_locked(self):
        self.assertTrue(self.registry["paper_trade_mode"])

    def test_advisory_only_is_locked(self):
        self.assertTrue(self.registry["advisory_only"])

    def test_database_writes_are_disabled(self):
        self.assertFalse(self.registry["direct_database_writes"])

    def test_known_registration_lookup(self):
        result = get_schema_registration(self.registry, "strategy_assignments_json", "1.3")
        self.assertEqual(result["schema_version"], "1.0")

    def test_unknown_artifact_is_rejected(self):
        with self.assertRaises(KeyError):
            get_schema_registration(self.registry, "unknown", "1.0")

    def test_unknown_version_is_rejected(self):
        with self.assertRaises(KeyError):
            get_schema_registration(self.registry, "strategy_assignments_json", "9.9")

    def test_schema_compatibility_true(self):
        self.assertTrue(is_schema_compatible(self.registry, "thesis_monitor_json", "1.4", "1.0"))

    def test_schema_compatibility_false_for_unknown_schema(self):
        self.assertFalse(is_schema_compatible(self.registry, "thesis_monitor_json", "1.4", "2.0"))

    def test_list_versions(self):
        self.assertEqual(list_artifact_versions(self.registry, "strategy_assignments_json"), ("1.3",))

    def test_latest_active_registration(self):
        result = get_latest_active_registration(self.registry, "executive_dashboard_json")
        self.assertEqual(result["artifact_version"], "1.0.1")

    def test_no_active_registration_is_rejected(self):
        changed = copy.deepcopy(self.registry)
        for item in changed["registrations"]:
            if item["artifact_id"] == "thesis_monitor_json":
                item["status"] = "DEPRECATED"
                item["replacement"] = "future"
        with self.assertRaises(KeyError):
            get_latest_active_registration(changed, "thesis_monitor_json")

    def test_duplicate_registration_is_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["registrations"].append(copy.deepcopy(changed["registrations"][0]))
        self.assertFalse(validate_schema_registry(changed).valid)

    def test_invalid_artifact_version_is_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["registrations"][0]["artifact_version"] = "v1"
        self.assertFalse(validate_schema_registry(changed).valid)

    def test_invalid_schema_version_is_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["registrations"][0]["schema_version"] = "latest"
        self.assertFalse(validate_schema_registry(changed).valid)

    def test_unsupported_format_is_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["registrations"][0]["format"] = "xml"
        self.assertFalse(validate_schema_registry(changed).valid)

    def test_json_requires_root_type(self):
        changed = copy.deepcopy(self.registry)
        del changed["registrations"][0]["root_type"]
        self.assertFalse(validate_schema_registry(changed).valid)

    def test_invalid_status_is_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["registrations"][0]["status"] = "UNKNOWN"
        self.assertFalse(validate_schema_registry(changed).valid)

    def test_deprecated_without_replacement_warns(self):
        changed = copy.deepcopy(self.registry)
        changed["registrations"][0]["status"] = "DEPRECATED"
        result = validate_schema_registry(changed)
        self.assertTrue(result.valid)
        self.assertTrue(result.warnings)

    def test_multiple_active_versions_warn(self):
        changed = copy.deepcopy(self.registry)
        extra = copy.deepcopy(changed["registrations"][0])
        extra["artifact_version"] = "1.4"
        changed["registrations"].append(extra)
        result = validate_schema_registry(changed)
        self.assertTrue(result.valid)
        self.assertTrue(result.warnings)

    def test_summary_counts(self):
        summary = build_registry_summary(self.registry)
        self.assertEqual(summary["registration_count"], 12)
        self.assertEqual(summary["artifact_count"], 12)

    def test_load_rejects_non_object_root(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps([]), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_schema_registry(path)

    def test_missing_required_registry_field_is_rejected(self):
        changed = copy.deepcopy(self.registry)
        del changed["registry_id"]
        self.assertFalse(validate_schema_registry(changed).valid)


if __name__ == "__main__":
    unittest.main()

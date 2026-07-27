from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from swing_trade_bot.swing_output_contract import (
    build_contract_summary,
    load_output_contract,
    validate_artifact_inventory,
    validate_output_contract,
)


class SwingOutputContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract_path = Path(__file__).resolve().parents[1] / "configs" / "swing_cio_output_contract.json"
        cls.contract = load_output_contract(cls.contract_path)

    def test_contract_loads(self) -> None:
        self.assertEqual(self.contract["contract_id"], "SWING-CIO-OUTPUT-CONTRACT")

    def test_committed_contract_is_valid(self) -> None:
        result = validate_output_contract(self.contract)
        self.assertTrue(result.valid, result.errors)

    def test_strict_versioning_is_required(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["versioning_policy"] = "REPOSITORY_VERSIONING"
        self.assertFalse(validate_output_contract(contract).valid)

    def test_artifact_versions_are_independent(self) -> None:
        versions = {item["artifact_version"] for item in self.contract["artifacts"]}
        self.assertGreater(len(versions), 1)

    def test_repository_version_cannot_override_artifacts(self) -> None:
        self.assertTrue(self.contract["compatibility_policy"]["repository_version_does_not_override_artifact_version"])

    def test_paper_trade_mode_is_locked(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["paper_trade_mode"] = False
        self.assertFalse(validate_output_contract(contract).valid)

    def test_advisory_only_is_locked(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["advisory_only"] = False
        self.assertFalse(validate_output_contract(contract).valid)

    def test_direct_database_writes_are_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["direct_database_writes"] = True
        self.assertFalse(validate_output_contract(contract).valid)

    def test_duplicate_artifact_id_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["artifacts"][1]["artifact_id"] = contract["artifacts"][0]["artifact_id"]
        self.assertFalse(validate_output_contract(contract).valid)

    def test_duplicate_path_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["artifacts"][1]["path"] = contract["artifacts"][0]["path"]
        self.assertFalse(validate_output_contract(contract).valid)

    def test_duplicate_columns_are_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        csv_artifact = next(item for item in contract["artifacts"] if item["format"] == "csv")
        csv_artifact["columns"].append(csv_artifact["columns"][0])
        self.assertFalse(validate_output_contract(contract).valid)

    def test_unsupported_format_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["artifacts"][0]["format"] = "xml"
        self.assertFalse(validate_output_contract(contract).valid)

    def test_extension_must_match_format(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["artifacts"][0]["path"] = "results/wrong.csv"
        self.assertFalse(validate_output_contract(contract).valid)

    def test_invalid_artifact_version_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["artifacts"][0]["artifact_version"] = "version-one"
        self.assertFalse(validate_output_contract(contract).valid)

    def test_invalid_schema_version_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["artifacts"][0]["schema_version"] = "1"
        self.assertFalse(validate_output_contract(contract).valid)

    def test_csv_requires_columns(self) -> None:
        contract = copy.deepcopy(self.contract)
        csv_artifact = next(item for item in contract["artifacts"] if item["format"] == "csv")
        csv_artifact.pop("columns")
        self.assertFalse(validate_output_contract(contract).valid)

    def test_json_requires_root_type(self) -> None:
        contract = copy.deepcopy(self.contract)
        json_artifact = next(item for item in contract["artifacts"] if item["format"] == "json")
        json_artifact.pop("root_type")
        self.assertFalse(validate_output_contract(contract).valid)

    def test_required_artifact_must_error_when_missing(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["artifacts"][0]["required"] = True
        contract["artifacts"][0]["missing_behavior"] = "ERROR"
        with tempfile.TemporaryDirectory() as directory:
            result = validate_artifact_inventory(contract, directory)
        self.assertFalse(result.valid)
        self.assertTrue(any("Missing artifact" in error for error in result.errors))

    def test_optional_artifact_warns_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = validate_artifact_inventory(self.contract, directory)
        self.assertTrue(result.valid)
        self.assertTrue(result.warnings)

    def test_existing_artifact_removes_its_missing_warning(self) -> None:
        contract = {**self.contract, "artifacts": [copy.deepcopy(self.contract["artifacts"][0])]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / contract["artifacts"][0]["path"]
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
            result = validate_artifact_inventory(contract, directory)
        self.assertTrue(result.valid)
        self.assertFalse(any(str(path) in warning for warning in result.warnings))

    def test_summary_lists_independent_versions(self) -> None:
        summary = build_contract_summary(self.contract)
        self.assertEqual(summary["versioning_policy"], "STRICT_ARTIFACT_VERSIONING")
        self.assertEqual(summary["artifact_count"], len(self.contract["artifacts"]))
        self.assertEqual(summary["artifact_versions"]["strategy_assignments_json"], "1.3")
        self.assertEqual(summary["artifact_versions"]["thesis_monitor_json"], "1.4")

    def test_contract_is_valid_json(self) -> None:
        parsed = json.loads(self.contract_path.read_text(encoding="utf-8"))
        self.assertIsInstance(parsed, dict)


if __name__ == "__main__":
    unittest.main()

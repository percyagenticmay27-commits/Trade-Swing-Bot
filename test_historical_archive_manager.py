import json
import zipfile
from datetime import date
from pathlib import Path

import historical_archive_manager as module


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_year(tmp_path: Path, year: int, symbol: str = "AMD") -> Path:
    source = tmp_path / f"source_{year}"
    _write_json(source / f"{symbol}_{year}.json", [{"symbol": symbol, "date": f"{year}-06-01", "return_percent": 12.5}])
    archive_root = tmp_path / "archives"
    module.create_year_archive(
        archive_year=year,
        source_root=str(source),
        archive_root=str(archive_root),
        market_era={"name": "AI Expansion"},
        policy_versions=["1.0"],
    )
    return archive_root / f"{year}.zip"


def test_public_functions_exist():
    for name in (
        "build_archive_manifest",
        "create_year_archive",
        "verify_archive",
        "build_historical_evidence_index",
        "retrieve_symbol_history",
        "plan_retention",
        "archive_heat_map",
        "classify_active_records",
        "build_historical_archive_report",
        "format_historical_archive_report_markdown",
        "format_historical_archive_report_html",
        "write_historical_archive_report",
        "build_and_write_historical_archive_report",
    ):
        assert callable(getattr(module, name))


def test_paper_only_flags():
    assert module.PAPER_TRADE_MODE is True
    assert module.LIVE_TRADING_ENABLED is False
    assert module.BROKER_EXECUTION_ENABLED is False
    assert module.REPORTING_ONLY is True


def test_manifest_counts_files_and_symbols(tmp_path):
    source = tmp_path / "source"
    _write_json(source / "AMD.json", [{"symbol": "AMD", "investment_id": "A1", "lesson": "test"}])
    manifest = module.build_archive_manifest(archive_year=2025, source_root=str(source))
    assert manifest["file_count"] == 1
    assert manifest["stock_count"] == 1
    assert manifest["symbols"] == ["AMD"]
    assert manifest["investment_count"] == 1
    assert manifest["lesson_count"] == 1


def test_create_archive_contains_manifest(tmp_path):
    archive = _make_year(tmp_path, 2025)
    assert archive.exists()
    with zipfile.ZipFile(archive, "r") as handle:
        assert "manifest.json" in handle.namelist()


def test_create_archive_refuses_overwrite(tmp_path):
    _make_year(tmp_path, 2025)
    source = tmp_path / "source_2025"
    try:
        module.create_year_archive(archive_year=2025, source_root=str(source), archive_root=str(tmp_path / "archives"))
    except FileExistsError:
        pass
    else:
        raise AssertionError("Expected FileExistsError")


def test_verify_archive_is_healthy(tmp_path):
    archive = _make_year(tmp_path, 2025)
    result = module.verify_archive(str(archive))
    assert result["exists"] is True
    assert result["readable"] is True
    assert result["manifest_present"] is True
    assert result["integrity_ok"] is True
    assert len(result["checksum_sha256"]) == 64


def test_verify_missing_archive(tmp_path):
    result = module.verify_archive(str(tmp_path / "missing.zip"))
    assert result["integrity_ok"] is False
    assert result["errors"]


def test_corrupt_archive_detected(tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"not a zip")
    result = module.verify_archive(str(path))
    assert result["integrity_ok"] is False


def test_evidence_index_lists_symbols_and_eras(tmp_path):
    _make_year(tmp_path, 2025, "AMD")
    _make_year(tmp_path, 2026, "NVDA")
    index = module.build_historical_evidence_index(str(tmp_path / "archives"))
    assert index["symbols"]["AMD"] == [2025]
    assert index["symbols"]["NVDA"] == [2026]
    assert index["market_eras"]["AI Expansion"] == [2025, 2026]


def test_multi_year_symbol_retrieval(tmp_path):
    for year in (2025, 2026, 2027):
        _make_year(tmp_path, year, "AMD")
    result = module.retrieve_symbol_history(
        symbol="AMD",
        years=[2025, 2026, 2027],
        archive_root=str(tmp_path / "archives"),
        requester="Stock Memory Engine",
        reason="Three-year tendency analysis",
    )
    assert len(result["records"]) == 3
    assert {row["archive_year"] for row in result["records"]} == {2025, 2026, 2027}


def test_retrieval_cleans_temporary_workspace(tmp_path):
    _make_year(tmp_path, 2025)
    result = module.retrieve_symbol_history(
        symbol="AMD", years=[2025], archive_root=str(tmp_path / "archives"), requester="Test", reason="Test"
    )
    assert result["access"]["temporary_workspace_removed"] is True


def test_read_only_retrieval_does_not_modify_archive(tmp_path):
    archive = _make_year(tmp_path, 2025)
    before = module.verify_archive(str(archive))["checksum_sha256"]
    result = module.retrieve_symbol_history(
        symbol="AMD", years=[2025], archive_root=str(tmp_path / "archives"), requester="Test", reason="Read only"
    )
    after = module.verify_archive(str(archive))["checksum_sha256"]
    assert before == after
    assert result["access"]["original_archives_modified"] is False
    assert result["access"]["integrity_verified"] is True


def test_access_log_written(tmp_path):
    _make_year(tmp_path, 2025)
    log = tmp_path / "logs" / "archive_access.json"
    module.retrieve_symbol_history(
        symbol="AMD",
        years=[2025],
        archive_root=str(tmp_path / "archives"),
        requester="Stock Memory Engine",
        reason="Thesis validation",
        access_log_path=str(log),
    )
    payload = json.loads(log.read_text(encoding="utf-8"))
    assert payload[0]["symbol"] == "AMD"
    assert payload[0]["requester"] == "Stock Memory Engine"


def test_missing_year_is_reported_not_fatal(tmp_path):
    _make_year(tmp_path, 2025)
    result = module.retrieve_symbol_history(
        symbol="AMD", years=[2025, 2024], archive_root=str(tmp_path / "archives"), requester="Test", reason="Test"
    )
    assert len(result["records"]) == 1
    assert result["access"]["errors"]


def test_blank_symbol_rejected(tmp_path):
    try:
        module.retrieve_symbol_history(
            symbol="", years=[2025], archive_root=str(tmp_path), requester="Test", reason="Test"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")


def test_retention_plan_keeps_latest_five(tmp_path):
    archive_root = tmp_path / "archives"
    archive_root.mkdir()
    for year in range(2020, 2027):
        (archive_root / f"{year}.zip").write_bytes(b"")
    plan = module.plan_retention(str(archive_root))
    assert plan["retained_years"] == [2022, 2023, 2024, 2025, 2026]
    assert plan["deletion_candidates"] == [2020, 2021]
    assert plan["investor_approval_required_before_deletion"] is True


def test_retention_does_not_delete_files(tmp_path):
    archive_root = tmp_path / "archives"
    archive_root.mkdir()
    for year in range(2020, 2027):
        (archive_root / f"{year}.zip").write_bytes(b"")
    module.plan_retention(str(archive_root))
    assert len(list(archive_root.glob("*.zip"))) == 7


def test_heat_map_counts_accesses():
    log = [
        {"archives_accessed": ["/a/2025.zip", "/a/2026.zip"], "reason": "Stock Memory"},
        {"archives_accessed": ["/a/2025.zip"], "reason": "Stock Memory"},
    ]
    heat = module.archive_heat_map(log)
    assert heat[0]["archive"] == "2025.zip"
    assert heat[0]["access_count"] == 2
    assert heat[0]["primary_reason"] == "Stock Memory"


def test_classify_active_records():
    records = [
        {"date": "2026-07-01", "symbol": "AMD"},
        {"date": "2024-01-01", "symbol": "NVDA"},
        {"symbol": "PLTR"},
    ]
    result = module.classify_active_records(records, as_of=date(2026, 7, 14))
    assert len(result["active_records"]) == 1
    assert len(result["archive_candidates"]) == 1
    assert len(result["undated_records"]) == 1


def test_report_empty_archive_root_is_healthy(tmp_path):
    report = module.build_historical_archive_report(archive_root=str(tmp_path / "archives"))
    assert report["archive_health_percent"] == 100.0
    assert report["archive_health_label"] == "HEALTHY"
    assert report["errors"] == []


def test_report_detects_bad_archive(tmp_path):
    archive_root = tmp_path / "archives"
    archive_root.mkdir()
    (archive_root / "2025.zip").write_bytes(b"bad")
    report = module.build_historical_archive_report(archive_root=str(archive_root))
    assert report["archive_health_percent"] == 0.0
    assert report["archive_health_label"] == "ATTENTION_REQUIRED"
    assert report["warnings"]


def test_governance_rules_locked(tmp_path):
    report = module.build_historical_archive_report(archive_root=str(tmp_path / "archives"))
    governance = report["governance"]
    assert governance["read_only_retrieval_modifies_archives"] is False
    assert governance["temporary_copies_deleted_after_analysis"] is True
    assert governance["recompression_required_after_read_only_retrieval"] is False
    assert governance["investor_approval_required_before_archive_deletion"] is True
    assert governance["strategic_policy_changes_allowed"] is False


def test_markdown_contains_storage_and_retrieval_rules(tmp_path):
    report = module.build_historical_archive_report(archive_root=str(tmp_path / "archives"))
    markdown = module.format_historical_archive_report_markdown(report)
    assert "Storage Policy" in markdown
    assert "Retrieval Rules" in markdown
    assert "temporary extracted working copies" in markdown


def test_html_contains_title(tmp_path):
    report = module.build_historical_archive_report(archive_root=str(tmp_path / "archives"))
    rendered = module.format_historical_archive_report_html(report)
    assert "<!doctype html>" in rendered.lower()
    assert "Historical Archive Manager" in rendered


def test_write_outputs(tmp_path):
    output = tmp_path / "out"
    report = module.write_historical_archive_report(
        {"archive_root": str(tmp_path / "archives")}, root_path=str(output)
    )
    assert report["module_name"] == module.MODULE_NAME
    assert (output / "archive_manager.json").exists()
    assert (output / "archive_manager.md").exists()
    assert (output / "archive_manager.html").exists()


def test_custom_output_names(tmp_path):
    module.write_historical_archive_report(
        {"archive_root": str(tmp_path / "archives")},
        root_path=str(tmp_path),
        output_files={"json": "custom.json", "markdown": "custom.md", "html": "custom.html"},
    )
    assert (tmp_path / "custom.json").exists()
    assert (tmp_path / "custom.md").exists()
    assert (tmp_path / "custom.html").exists()


def test_invalid_payload_rejected(tmp_path):
    try:
        module.write_historical_archive_report("invalid", root_path=str(tmp_path))
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")


def test_no_broker_or_order_execution_imports():
    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    forbidden = ["import robin_stocks", "import alpaca", "submit_order(", "place_order(", "broker.login"]
    assert not any(item in source for item in forbidden)


def test_constants_match_retention_policy():
    assert module.ACTIVE_HISTORY_DAYS == 365
    assert module.MAX_ARCHIVED_YEARS == 5

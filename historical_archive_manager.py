"""Paper-only historical archive manager for the AI CIO platform.

Maintains a rolling active-history window, annual ZIP archives, manifests,
checksums, evidence indexes, read-only multi-year retrieval, integrity checks,
access logs, retention planning, market-era metadata, and archive heat maps.
"""
from __future__ import annotations

import hashlib
import html
import json
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

MODULE_NAME = "historical_archive_manager"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
PAPER_TRADE_MODE = True
LIVE_TRADING_ENABLED = False
BROKER_EXECUTION_ENABLED = False
REPORTING_ONLY = True
ACTIVE_HISTORY_DAYS = 365
MAX_ARCHIVED_YEARS = 5
DEFAULT_OUTPUT_FILES = {
    "json": "archive_manager.json",
    "markdown": "archive_manager.md",
    "html": "archive_manager.html",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _year_from_name(path: Path) -> Optional[int]:
    try:
        return int(path.stem)
    except (TypeError, ValueError):
        return None


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _record_date(record: Mapping[str, Any]) -> Optional[date]:
    raw = record.get("date") or record.get("timestamp") or record.get("generated_at_utc")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            return None


def build_archive_manifest(
    *,
    archive_year: int,
    source_root: str,
    market_era: Optional[Mapping[str, Any]] = None,
    policy_versions: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    root = Path(source_root)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    symbols: set[str] = set()
    investment_count = 0
    lesson_count = 0
    for path in files:
        payload = _safe_json(path, None) if path.suffix.lower() == ".json" else None
        rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, Mapping) else []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            symbol = _normalize_symbol(row.get("symbol") or row.get("ticker") or row.get("underlying"))
            if symbol:
                symbols.add(symbol)
            if row.get("investment_id") or row.get("allocation_id"):
                investment_count += 1
            if row.get("lesson") or row.get("lesson_id"):
                lesson_count += 1
    return {
        "archive_version": MODULE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "archive_year": int(archive_year),
        "created_at_utc": _now(),
        "file_count": len(files),
        "stock_count": len(symbols),
        "symbols": sorted(symbols),
        "investment_count": investment_count,
        "lesson_count": lesson_count,
        "policy_versions": sorted(set(str(item) for item in (policy_versions or []))),
        "market_era": dict(market_era or {}),
        "date_range": {"start": f"{archive_year}-01-01", "end": f"{archive_year}-12-31"},
    }


def create_year_archive(
    *,
    archive_year: int,
    source_root: str,
    archive_root: str,
    market_era: Optional[Mapping[str, Any]] = None,
    policy_versions: Optional[Sequence[str]] = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    source = Path(source_root)
    destination_root = Path(archive_root)
    destination_root.mkdir(parents=True, exist_ok=True)
    archive_path = destination_root / f"{archive_year}.zip"
    if archive_path.exists() and not overwrite:
        raise FileExistsError(str(archive_path))
    manifest = build_archive_manifest(
        archive_year=archive_year,
        source_root=str(source),
        market_era=market_era,
        policy_versions=policy_versions,
    )
    temp_archive = archive_path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            archive.write(path, arcname=str(path.relative_to(source)))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    temp_archive.replace(archive_path)
    checksum = _sha256(archive_path)
    return {
        "archive_path": str(archive_path),
        "archive_year": archive_year,
        "checksum_sha256": checksum,
        "manifest": manifest,
        "created": True,
    }


def verify_archive(archive_path: str) -> dict[str, Any]:
    path = Path(archive_path)
    result = {
        "archive_path": str(path),
        "exists": path.exists(),
        "readable": False,
        "manifest_present": False,
        "integrity_ok": False,
        "checksum_sha256": "",
        "errors": [],
    }
    if not path.exists():
        result["errors"].append("Archive does not exist.")
        return result
    try:
        result["checksum_sha256"] = _sha256(path)
        with zipfile.ZipFile(path, "r") as archive:
            result["readable"] = True
            result["manifest_present"] = "manifest.json" in archive.namelist()
            corrupt = archive.testzip()
            if corrupt:
                result["errors"].append(f"Corrupt member: {corrupt}")
            if not result["manifest_present"]:
                result["errors"].append("manifest.json is missing.")
            result["integrity_ok"] = corrupt is None and result["manifest_present"]
    except (OSError, zipfile.BadZipFile) as exc:
        result["errors"].append(str(exc))
    return result


def build_historical_evidence_index(archive_root: str) -> dict[str, Any]:
    root = Path(archive_root)
    by_symbol: dict[str, list[int]] = defaultdict(list)
    by_market_era: dict[str, list[int]] = defaultdict(list)
    archives = []
    for archive_path in sorted(root.glob("*.zip")):
        year = _year_from_name(archive_path)
        verification = verify_archive(str(archive_path))
        manifest: Mapping[str, Any] = {}
        if verification["integrity_ok"]:
            with zipfile.ZipFile(archive_path, "r") as archive:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if year is not None:
            for symbol in manifest.get("symbols", []) if isinstance(manifest, Mapping) else []:
                by_symbol[_normalize_symbol(symbol)].append(year)
            era = manifest.get("market_era", {}) if isinstance(manifest, Mapping) else {}
            era_name = str(era.get("name", "")).strip() if isinstance(era, Mapping) else ""
            if era_name:
                by_market_era[era_name].append(year)
        archives.append({
            "year": year,
            "path": str(archive_path),
            "integrity_ok": verification["integrity_ok"],
            "checksum_sha256": verification["checksum_sha256"],
            "file_count": manifest.get("file_count", 0) if isinstance(manifest, Mapping) else 0,
        })
    return {
        "generated_at_utc": _now(),
        "archives": archives,
        "symbols": {key: sorted(set(value)) for key, value in sorted(by_symbol.items())},
        "market_eras": {key: sorted(set(value)) for key, value in sorted(by_market_era.items())},
    }


def retrieve_symbol_history(
    *,
    symbol: str,
    years: Sequence[int],
    archive_root: str,
    requester: str,
    reason: str,
    access_log_path: Optional[str] = None,
) -> dict[str, Any]:
    normalized = _normalize_symbol(symbol)
    if not normalized:
        raise ValueError("symbol is required")
    requested_years = sorted(set(int(year) for year in years))
    archive_root_path = Path(archive_root)
    records: list[dict[str, Any]] = []
    archives_accessed: list[str] = []
    errors: list[str] = []
    original_checksums: dict[str, str] = {}
    temporary_workspace_removed = False
    with tempfile.TemporaryDirectory(prefix="ai_cio_archive_") as temp_dir:
        workspace = Path(temp_dir)
        for year in requested_years:
            archive_path = archive_root_path / f"{year}.zip"
            verification = verify_archive(str(archive_path))
            if not verification["integrity_ok"]:
                errors.append(f"{year}: archive unavailable or invalid")
                continue
            original_checksums[str(archive_path)] = verification["checksum_sha256"]
            archives_accessed.append(str(archive_path))
            with zipfile.ZipFile(archive_path, "r") as archive:
                for member in archive.namelist():
                    if member.endswith("/") or member == "manifest.json":
                        continue
                    lowered = member.lower()
                    if normalized.lower() not in lowered and not lowered.endswith(".json"):
                        continue
                    extracted = Path(archive.extract(member, path=workspace / str(year)))
                    if extracted.suffix.lower() != ".json":
                        continue
                    payload = _safe_json(extracted, None)
                    candidates = payload if isinstance(payload, list) else [payload] if isinstance(payload, Mapping) else []
                    for candidate in candidates:
                        if not isinstance(candidate, Mapping):
                            continue
                        candidate_symbol = _normalize_symbol(candidate.get("symbol") or candidate.get("ticker") or candidate.get("underlying"))
                        text_match = normalized in json.dumps(candidate, sort_keys=True).upper()
                        if candidate_symbol == normalized or text_match:
                            row = dict(candidate)
                            row.setdefault("archive_year", year)
                            records.append(row)
        temporary_workspace_removed = True
    integrity_after = []
    for archive in archives_accessed:
        after = verify_archive(archive)
        integrity_after.append({
            "archive": archive,
            "integrity_ok": after["integrity_ok"],
            "unchanged": original_checksums.get(archive) == after["checksum_sha256"],
        })
    log_entry = {
        "accessed_at_utc": _now(),
        "requester": requester,
        "reason": reason,
        "symbol": normalized,
        "years_requested": requested_years,
        "archives_accessed": archives_accessed,
        "record_count": len(records),
        "temporary_workspace_removed": temporary_workspace_removed,
        "original_archives_modified": any(not item["unchanged"] for item in integrity_after),
        "integrity_verified": all(item["integrity_ok"] and item["unchanged"] for item in integrity_after),
        "errors": errors,
    }
    if access_log_path:
        log_path = Path(access_log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        existing = _safe_json(log_path, [])
        if not isinstance(existing, list):
            existing = []
        existing.append(log_entry)
        log_path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"records": records, "access": log_entry}


def plan_retention(archive_root: str, *, max_years: int = MAX_ARCHIVED_YEARS) -> dict[str, Any]:
    years = sorted(year for path in Path(archive_root).glob("*.zip") if (year := _year_from_name(path)) is not None)
    retained = years[-max_years:] if max_years > 0 else []
    candidates = years[:-max_years] if max_years > 0 else years
    return {
        "archive_years": years,
        "retained_years": retained,
        "deletion_candidates": candidates,
        "investor_approval_required_before_deletion": True,
    }


def archive_heat_map(access_log: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    reasons: dict[str, Counter[str]] = defaultdict(Counter)
    for item in access_log:
        if not isinstance(item, Mapping):
            continue
        reason = str(item.get("reason", "Unspecified"))
        for archive in item.get("archives_accessed", []) if isinstance(item.get("archives_accessed"), list) else []:
            name = Path(str(archive)).name
            counts[name] += 1
            reasons[name][reason] += 1
    return [
        {
            "archive": archive,
            "access_count": count,
            "primary_reason": reasons[archive].most_common(1)[0][0] if reasons[archive] else "Unspecified",
        }
        for archive, count in counts.most_common()
    ]


def classify_active_records(records: Sequence[Mapping[str, Any]], *, as_of: Optional[date] = None) -> dict[str, Any]:
    cutoff = (as_of or date.today()) - timedelta(days=ACTIVE_HISTORY_DAYS)
    active, archive_candidates, undated = [], [], []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        record_date = _record_date(record)
        if record_date is None:
            undated.append(dict(record))
        elif record_date >= cutoff:
            active.append(dict(record))
        else:
            archive_candidates.append(dict(record))
    return {
        "cutoff_date": cutoff.isoformat(),
        "active_records": active,
        "archive_candidates": archive_candidates,
        "undated_records": undated,
    }


def build_historical_archive_report(
    *,
    archive_root: str = "history/archive",
    access_log: Optional[Sequence[Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    index = build_historical_evidence_index(archive_root)
    retention = plan_retention(archive_root)
    verifications = [verify_archive(item["path"]) for item in index["archives"]]
    healthy = sum(1 for item in verifications if item["integrity_ok"])
    total = len(verifications)
    health_percent = 100.0 if total == 0 else round(healthy / total * 100.0, 2)
    return {
        "module_name": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _now(),
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "reporting_only": True,
        "active_history_days": ACTIVE_HISTORY_DAYS,
        "maximum_archived_years": MAX_ARCHIVED_YEARS,
        "archive_health_percent": health_percent,
        "archive_health_label": "HEALTHY" if health_percent == 100.0 else "ATTENTION_REQUIRED",
        "historical_evidence_index": index,
        "retention_plan": retention,
        "archive_heat_map": archive_heat_map(access_log or []),
        "governance": {
            "read_only_retrieval_modifies_archives": False,
            "temporary_copies_deleted_after_analysis": True,
            "recompression_required_after_read_only_retrieval": False,
            "investor_approval_required_before_archive_deletion": True,
            "strategic_policy_changes_allowed": False,
        },
        "warnings": [] if health_percent == 100.0 else ["One or more archives failed integrity validation."],
        "errors": [],
    }


def format_historical_archive_report_markdown(report: Mapping[str, Any]) -> str:
    retention = report.get("retention_plan", {}) if isinstance(report.get("retention_plan"), Mapping) else {}
    lines = [
        "# Historical Archive Manager", "",
        f"**Archive Health:** {report.get('archive_health_percent', 0):.2f}% ({report.get('archive_health_label', 'UNKNOWN')})", "",
        "## Storage Policy", "",
        f"- Active history: {report.get('active_history_days', ACTIVE_HISTORY_DAYS)} days",
        f"- Maximum archived years: {report.get('maximum_archived_years', MAX_ARCHIVED_YEARS)}",
        f"- Archived years: {', '.join(map(str, retention.get('archive_years', []))) or 'None'}",
        f"- Deletion candidates: {', '.join(map(str, retention.get('deletion_candidates', []))) or 'None'}",
        "- Archive deletion requires investor approval.", "",
        "## Archive Heat Map", "",
        "| Archive | Accesses | Primary Reason |", "|---|---:|---|",
    ]
    heat = report.get("archive_heat_map", []) if isinstance(report.get("archive_heat_map"), list) else []
    if heat:
        for item in heat:
            lines.append(f"| {item.get('archive', '')} | {item.get('access_count', 0)} | {item.get('primary_reason', '')} |")
    else:
        lines.append("| None | 0 | No archive access recorded |")
    lines.extend([
        "", "## Retrieval Rules", "",
        "- Multi-year requests may combine two or three annual ZIP archives.",
        "- Only temporary extracted working copies are deleted.",
        "- Original archives remain unchanged during read-only retrieval.",
        "- ZIP archives are rebuilt only during controlled maintenance.",
        "", "## Paper-Only Safety", "",
        "This module stores and retrieves historical evidence only. It cannot place orders, contact a brokerage, or change investment policy.", "",
    ])
    return "\n".join(lines)


def format_historical_archive_report_html(report: Mapping[str, Any]) -> str:
    markdown = format_historical_archive_report_markdown(report)
    return "<!doctype html><html><head><meta charset='utf-8'><title>Historical Archive Manager</title><style>body{font-family:Arial,sans-serif;max-width:1100px;margin:0 auto;padding:32px;background:#f5f7fb;color:#172033}pre{white-space:pre-wrap;background:white;padding:30px;border-radius:14px;box-shadow:0 4px 18px rgba(0,0,0,.08);line-height:1.55}</style></head><body><pre>" + html.escape(markdown) + "</pre></body></html>"


def write_historical_archive_report(
    payload: Mapping[str, Any],
    root_path: str = ".",
    output_files: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    report = build_historical_archive_report(**dict(payload))
    root = Path(root_path)
    root.mkdir(parents=True, exist_ok=True)
    files = dict(DEFAULT_OUTPUT_FILES)
    if output_files:
        files.update(output_files)
    (root / files["json"]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / files["markdown"]).write_text(format_historical_archive_report_markdown(report), encoding="utf-8")
    (root / files["html"]).write_text(format_historical_archive_report_html(report), encoding="utf-8")
    return report


def build_and_write_historical_archive_report(payload: Mapping[str, Any], root_path: str = ".", output_files: Optional[Mapping[str, str]] = None) -> dict[str, Any]:
    return write_historical_archive_report(payload, root_path, output_files)


if __name__ == "__main__":
    result = write_historical_archive_report({"archive_root": "history/archive"})
    print(f"Historical Archive Manager: {result['archive_health_label']}")

"""Read-only presentation adapter for strict-versioned Swing CIO artifacts."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_NAME = "swing_cio_presentation_adapter"
MODULE_VERSION = "1.0.0"
ADAPTER_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class AdapterValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


@dataclass(frozen=True, slots=True)
class PresentationSection:
    presentation_id: str
    artifact_id: str
    artifact_version: str
    dashboard_destination: str
    title: str
    status: str
    source_path: str
    record_count: int
    summary: dict[str, object]
    records: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["records"] = list(self.records)
        value["warnings"] = list(self.warnings)
        return value


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_adapter_config(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Adapter config root must be an object")
    return payload


def validate_adapter_config(config: Mapping[str, Any]) -> AdapterValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    for field in ("adapter_schema_version", "adapter_id", "plugin_id", "adapter_version", "outputs", "presentations"):
        if config.get(field) in (None, ""):
            errors.append(f"Missing required adapter field: {field}")
    if config.get("adapter_schema_version") != ADAPTER_SCHEMA_VERSION:
        errors.append(f"Unsupported adapter_schema_version: {config.get('adapter_schema_version')}")
    for field in ("paper_trade_mode", "advisory_only", "read_only_sources"):
        if config.get(field) is not True:
            errors.append(f"{field} must be true")
    if config.get("direct_database_writes") is not False:
        errors.append("direct_database_writes must be false")

    outputs = config.get("outputs")
    if not isinstance(outputs, Mapping):
        errors.append("outputs must be an object")
    else:
        if not str(outputs.get("json", "")).lower().endswith(".json"):
            errors.append("outputs.json must use .json")
        if not str(outputs.get("markdown", "")).lower().endswith(".md"):
            errors.append("outputs.markdown must use .md")

    presentations = config.get("presentations")
    if not isinstance(presentations, list) or not presentations:
        errors.append("presentations must be a non-empty list")
        presentations = []
    presentation_ids: set[str] = set()
    keys: set[tuple[str, str]] = set()
    for index, item in enumerate(presentations):
        prefix = f"presentations[{index}]"
        if not isinstance(item, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("presentation_id", "artifact_id", "artifact_version", "source_path", "dashboard_destination", "title"):
            if item.get(field) in (None, ""):
                errors.append(f"{prefix} missing required field: {field}")
        presentation_id = str(item.get("presentation_id", ""))
        if presentation_id in presentation_ids:
            errors.append(f"Duplicate presentation_id: {presentation_id}")
        presentation_ids.add(presentation_id)
        key = (str(item.get("artifact_id", "")), str(item.get("artifact_version", "")))
        if key in keys:
            errors.append(f"Duplicate artifact/version presentation: {key[0]} {key[1]}")
        keys.add(key)
        key_fields = item.get("key_fields", [])
        if not isinstance(key_fields, list) or any(not isinstance(value, str) or not value for value in key_fields):
            errors.append(f"{prefix}.key_fields must be a list of non-empty strings")
        elif len(key_fields) != len(set(key_fields)):
            errors.append(f"{prefix}.key_fields contains duplicates")
        if item.get("record_path") is not None and not isinstance(item.get("record_path"), str):
            errors.append(f"{prefix}.record_path must be a string or null")
        if item.get("required") not in {True, False}:
            errors.append(f"{prefix}.required must be boolean")
    return AdapterValidationResult(not errors, tuple(errors), tuple(warnings))


def build_presentation(
    config: Mapping[str, Any],
    repository_root: str | Path,
    *,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    validation = validate_adapter_config(config)
    if not validation.valid:
        raise ValueError("Invalid adapter config: " + "; ".join(validation.errors))
    root = Path(repository_root)
    sections: list[PresentationSection] = []
    errors: list[str] = []
    warnings: list[str] = list(validation.warnings)
    for definition in config.get("presentations", []):
        if not isinstance(definition, Mapping):
            continue
        section = _build_section(definition, root, registry)
        sections.append(section)
        warnings.extend(section.warnings)
        if section.status == "ERROR":
            errors.append(f"Unable to present required artifact: {section.source_path}")
    return {
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter_version": MODULE_VERSION,
        "plugin_id": config.get("plugin_id"),
        "generated_at_utc": _now(),
        "paper_trade_mode": True,
        "advisory_only": True,
        "source_files_modified": False,
        "status": "ERROR" if errors else "READY_WITH_WARNINGS" if warnings else "READY",
        "section_count": len(sections),
        "available_section_count": sum(section.status == "AVAILABLE" for section in sections),
        "errors": errors,
        "warnings": warnings,
        "sections": [section.to_dict() for section in sections],
    }


def _build_section(definition: Mapping[str, Any], root: Path, registry: Mapping[str, Any] | None) -> PresentationSection:
    source_path = str(definition.get("source_path", ""))
    path = root / source_path
    local_warnings: list[str] = []
    required = definition.get("required") is True
    if registry is not None and not _is_registered(registry, str(definition.get("artifact_id")), str(definition.get("artifact_version"))):
        message = f"Unregistered artifact/version: {definition.get('artifact_id')} {definition.get('artifact_version')}"
        return _empty_section(definition, "ERROR" if required else "UNAVAILABLE", message)
    if not path.exists():
        message = f"Missing {'required' if required else 'optional'} artifact: {source_path}"
        return _empty_section(definition, "ERROR" if required else "UNAVAILABLE", message)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _empty_section(definition, "ERROR" if required else "UNAVAILABLE", f"Unreadable artifact {source_path}: {exc}")

    record_path = definition.get("record_path")
    key_fields = [str(value) for value in definition.get("key_fields", [])]
    records: list[dict[str, object]] = []
    if record_path:
        raw_records = payload.get(record_path, []) if isinstance(payload, Mapping) else []
        if not isinstance(raw_records, list):
            local_warnings.append(f"Record path {record_path} is not a list in {source_path}")
        else:
            for raw in raw_records:
                if isinstance(raw, Mapping):
                    records.append({field: raw.get(field) for field in key_fields})
    summary = _summarize_payload(payload, len(records))
    return PresentationSection(
        presentation_id=str(definition.get("presentation_id")),
        artifact_id=str(definition.get("artifact_id")),
        artifact_version=str(definition.get("artifact_version")),
        dashboard_destination=str(definition.get("dashboard_destination")),
        title=str(definition.get("title")),
        status="AVAILABLE",
        source_path=source_path,
        record_count=len(records),
        summary=summary,
        records=tuple(records),
        warnings=tuple(local_warnings),
    )


def _empty_section(definition: Mapping[str, Any], status: str, warning: str) -> PresentationSection:
    return PresentationSection(
        presentation_id=str(definition.get("presentation_id")),
        artifact_id=str(definition.get("artifact_id")),
        artifact_version=str(definition.get("artifact_version")),
        dashboard_destination=str(definition.get("dashboard_destination")),
        title=str(definition.get("title")),
        status=status,
        source_path=str(definition.get("source_path")),
        record_count=0,
        summary={},
        records=(),
        warnings=(warning,),
    )


def _summarize_payload(payload: Any, record_count: int) -> dict[str, object]:
    if isinstance(payload, Mapping):
        scalar_values = {
            str(key): value
            for key, value in payload.items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
        scalar_values["record_count"] = record_count
        return scalar_values
    if isinstance(payload, list):
        return {"root_type": "array", "item_count": len(payload), "record_count": record_count}
    return {"root_type": type(payload).__name__, "record_count": record_count}


def _is_registered(registry: Mapping[str, Any], artifact_id: str, artifact_version: str) -> bool:
    registrations = registry.get("registrations", [])
    return any(
        isinstance(item, Mapping)
        and item.get("artifact_id") == artifact_id
        and item.get("artifact_version") == artifact_version
        for item in registrations
    )


def format_presentation_markdown(presentation: Mapping[str, Any]) -> str:
    lines = [
        "# Swing CIO Presentation",
        "",
        "Paper-only advisory presentation. Source reports are not modified.",
        "",
        f"- Status: {presentation.get('status')}",
        f"- Generated: {presentation.get('generated_at_utc')}",
        f"- Available sections: {presentation.get('available_section_count')} / {presentation.get('section_count')}",
        "",
    ]
    for section in presentation.get("sections", []):
        if not isinstance(section, Mapping):
            continue
        lines.extend([
            f"## {section.get('title')}",
            "",
            f"- Status: {section.get('status')}",
            f"- Artifact: `{section.get('artifact_id')}` version `{section.get('artifact_version')}`",
            f"- Dashboard: {section.get('dashboard_destination')}",
            f"- Records: {section.get('record_count')}",
            "",
        ])
        for warning in section.get("warnings", []):
            lines.append(f"> Warning: {warning}")
        records = section.get("records", [])
        if records:
            fields = list(records[0].keys())
            lines.extend(["", "| " + " | ".join(fields) + " |", "|" + "|".join("---" for _ in fields) + "|"])
            for record in records:
                lines.append("| " + " | ".join(str(record.get(field, "")) for field in fields) + " |")
        lines.append("")
    return "\n".join(lines)


def write_presentation_outputs(output_dir: str | Path, presentation: Mapping[str, Any]) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "swing_cio_presentation.json"
    markdown_path = destination / "swing_cio_presentation.md"
    json_path.write_text(json.dumps(dict(presentation), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(format_presentation_markdown(presentation), encoding="utf-8")
    return json_path, markdown_path

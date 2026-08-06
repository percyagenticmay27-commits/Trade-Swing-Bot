"""Discover and resolve authoritative Enterprise strategy allocation evidence.

The Dividend-hosted AI CIO owns total strategy capital. This module reads its
strategy-level evidence only and never writes to the external repository. Swing
security-level portfolio allocations are deliberately excluded as an Enterprise
capital source.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

STRATEGY_ID = "SWING-001"
DEFAULT_AI_CIO_REPOSITORY = Path(
    os.environ.get("AI_CIO_REPOSITORY", "/home/tradebot/Trade-Dividend-Bot")
)
DEFAULT_AI_CIO_REGISTRY_RELATIVE_PATH = Path(
    "results/enterprise_registry_strategy_evidence.json"
)
ALLOCATION_FIELDS: tuple[str, ...] = (
    "allocated_capital",
    "allocation_amount",
    "capital_allocation",
    "strategy_allocation",
    "approved_capital",
)


def load_json_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {source}")
    return payload


def _finite_nonnegative(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _allocation_field_from_record(
    record: Mapping[str, Any],
    *,
    strategy_id: str,
    allocation_fields: Sequence[str],
    schema_path: str,
) -> tuple[float, str]:
    for field in allocation_fields:
        if field in record:
            allocated = _finite_nonnegative(record.get(field))
            if allocated is None:
                raise ValueError(
                    f"{schema_path}[{strategy_id!r}].{field} must be finite and nonnegative"
                )
            return allocated, field
    raise ValueError(
        f"{schema_path}[{strategy_id!r}] is missing a supported allocation field: "
        + ", ".join(allocation_fields)
    )


def _matching_record(
    records: object,
    *,
    strategy_id: str,
    schema_path: str,
) -> tuple[Mapping[str, Any], int] | None:
    if not isinstance(records, list):
        return None
    matches = [
        (item, index)
        for index, item in enumerate(records)
        if isinstance(item, Mapping)
        and str(item.get("strategy_id", "")).strip() == strategy_id
    ]
    if not matches:
        raise ValueError(f"{schema_path} record for {strategy_id!r} is required")
    if len(matches) > 1:
        raise ValueError(f"{schema_path} contains duplicate {strategy_id!r} records")
    return matches[0]


def _nested_strategy_kpi_candidates(
    value: object,
    *,
    strategy_id: str,
    path: str = "$",
    depth: int = 0,
) -> list[tuple[int, str, Mapping[str, Any]]]:
    """Find exact strategy records in nested AI CIO evidence containers."""
    matches: list[tuple[int, str, Mapping[str, Any]]] = []
    if isinstance(value, Mapping):
        strategy_kpis = value.get("strategy_kpis")
        if isinstance(strategy_kpis, list):
            for index, item in enumerate(strategy_kpis):
                if (
                    isinstance(item, Mapping)
                    and str(item.get("strategy_id", "")).strip() == strategy_id
                ):
                    matches.append((depth, f"{path}.strategy_kpis[{index}]", item))
        for key, child in value.items():
            if key == "strategy_kpis":
                continue
            matches.extend(
                _nested_strategy_kpi_candidates(
                    child,
                    strategy_id=strategy_id,
                    path=f"{path}.{key}",
                    depth=depth + 1,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(
                _nested_strategy_kpi_candidates(
                    child,
                    strategy_id=strategy_id,
                    path=f"{path}[{index}]",
                    depth=depth + 1,
                )
            )
    return matches


def resolve_strategy_allocation_evidence(
    payload: Mapping[str, Any],
    strategy_id: str = STRATEGY_ID,
    *,
    allocation_fields: Sequence[str] = ALLOCATION_FIELDS,
) -> dict[str, Any]:
    """Resolve allocation plus exact schema and JSON-path provenance.

    Resolution order is deterministic:
    1. Direct AI CIO evidence ``payload.strategy_kpis[]``.
    2. Shallowest nested AI CIO evidence containing ``strategy_kpis[]``.
    3. Current registry ``strategy_plugins[]``.
    4. Legacy ``strategy_allocations[strategy_id]``.
    """
    evidence_payload = payload.get("payload")
    strategy_kpis = (
        evidence_payload.get("strategy_kpis")
        if isinstance(evidence_payload, Mapping)
        else None
    )
    direct = _matching_record(
        strategy_kpis,
        strategy_id=strategy_id,
        schema_path="payload.strategy_kpis",
    )
    if direct is not None:
        record, index = direct
        record_path = f"$.payload.strategy_kpis[{index}]"
        allocated, field = _allocation_field_from_record(
            record,
            strategy_id=strategy_id,
            allocation_fields=allocation_fields,
            schema_path=record_path,
        )
        return {
            "allocated_capital": allocated,
            "allocation_evidence_schema": "payload.strategy_kpis",
            "allocation_source_json_path": f"{record_path}.{field}",
            "allocation_field": field,
        }

    candidates = _nested_strategy_kpi_candidates(payload, strategy_id=strategy_id)
    if candidates:
        shallowest_depth = min(depth for depth, _, _ in candidates)
        shallowest = [item for item in candidates if item[0] == shallowest_depth]
        resolved: list[tuple[str, float, str]] = []
        for _, record_path, record in shallowest:
            allocated, field = _allocation_field_from_record(
                record,
                strategy_id=strategy_id,
                allocation_fields=allocation_fields,
                schema_path=record_path,
            )
            resolved.append((record_path, allocated, field))
        distinct_values = {allocation for _, allocation, _ in resolved}
        if len(distinct_values) > 1:
            paths = ", ".join(path for path, _, _ in resolved)
            raise ValueError(
                f"Conflicting nested AI CIO allocation evidence for {strategy_id!r}: {paths}"
            )
        record_path, allocated, field = resolved[0]
        return {
            "allocated_capital": allocated,
            "allocation_evidence_schema": "nested.payload.strategy_kpis",
            "allocation_source_json_path": f"{record_path}.{field}",
            "allocation_field": field,
        }

    plugins = _matching_record(
        payload.get("strategy_plugins"),
        strategy_id=strategy_id,
        schema_path="strategy_plugins",
    )
    if plugins is not None:
        record, index = plugins
        record_path = f"$.strategy_plugins[{index}]"
        allocated, field = _allocation_field_from_record(
            record,
            strategy_id=strategy_id,
            allocation_fields=allocation_fields,
            schema_path=record_path,
        )
        return {
            "allocated_capital": allocated,
            "allocation_evidence_schema": "strategy_plugins",
            "allocation_source_json_path": f"{record_path}.{field}",
            "allocation_field": field,
        }

    legacy = payload.get("strategy_allocations")
    if isinstance(legacy, Mapping):
        allocated = _finite_nonnegative(legacy.get(strategy_id))
        if allocated is None:
            raise ValueError(f"strategy_allocations[{strategy_id!r}] is required")
        return {
            "allocated_capital": allocated,
            "allocation_evidence_schema": "strategy_allocations",
            "allocation_source_json_path": f"$.strategy_allocations.{strategy_id}",
            "allocation_field": strategy_id,
        }

    raise ValueError(
        "Enterprise allocation evidence must contain direct or nested strategy_kpis, "
        "strategy_plugins, or strategy_allocations"
    )


def resolve_strategy_allocation(
    payload: Mapping[str, Any],
    strategy_id: str = STRATEGY_ID,
    *,
    allocation_fields: Sequence[str] = ALLOCATION_FIELDS,
) -> float:
    """Resolve the authoritative numeric strategy allocation."""
    evidence = resolve_strategy_allocation_evidence(
        payload,
        strategy_id,
        allocation_fields=allocation_fields,
    )
    return float(evidence["allocated_capital"])


def discover_strategy_allocations_file(
    explicit_path: str | Path | None = None,
    *,
    ai_cio_repository: str | Path = DEFAULT_AI_CIO_REPOSITORY,
    registry_relative_path: str | Path = DEFAULT_AI_CIO_REGISTRY_RELATIVE_PATH,
) -> Path:
    """Return an explicit source or the Dividend-hosted AI CIO evidence artifact."""
    if explicit_path is not None:
        source = Path(explicit_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Strategy allocation evidence not found: {source}")
        return source

    repository = Path(ai_cio_repository).expanduser().resolve()
    relative = Path(registry_relative_path)
    if relative.is_absolute():
        raise ValueError("AI CIO evidence path must be relative to the AI CIO repository")
    source = (repository / relative).resolve()
    try:
        source.relative_to(repository)
    except ValueError as exc:
        raise ValueError("AI CIO evidence path escapes the AI CIO repository") from exc
    if not source.is_file():
        raise FileNotFoundError(f"AI CIO strategy evidence not found: {source}")
    return source


def load_discovered_strategy_allocations(
    explicit_path: str | Path | None = None,
    *,
    ai_cio_repository: str | Path = DEFAULT_AI_CIO_REPOSITORY,
    registry_relative_path: str | Path = DEFAULT_AI_CIO_REGISTRY_RELATIVE_PATH,
) -> tuple[dict[str, Any], Path]:
    source = discover_strategy_allocations_file(
        explicit_path,
        ai_cio_repository=ai_cio_repository,
        registry_relative_path=registry_relative_path,
    )
    return load_json_object(source), source

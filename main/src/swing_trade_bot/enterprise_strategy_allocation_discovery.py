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


def _allocation_from_record(
    record: Mapping[str, Any],
    *,
    strategy_id: str,
    allocation_fields: Sequence[str],
    schema_path: str,
) -> float:
    for field in allocation_fields:
        if field in record:
            allocated = _finite_nonnegative(record.get(field))
            if allocated is None:
                raise ValueError(
                    f"{schema_path}[{strategy_id!r}].{field} must be finite and nonnegative"
                )
            return allocated
    raise ValueError(
        f"{schema_path}[{strategy_id!r}] is missing a supported allocation field: "
        + ", ".join(allocation_fields)
    )


def _allocation_from_records(
    records: object,
    *,
    strategy_id: str,
    allocation_fields: Sequence[str],
    schema_path: str,
) -> float | None:
    if not isinstance(records, list):
        return None
    matches = [
        item
        for item in records
        if isinstance(item, Mapping)
        and str(item.get("strategy_id", "")).strip() == strategy_id
    ]
    if not matches:
        raise ValueError(f"{schema_path} record for {strategy_id!r} is required")
    if len(matches) > 1:
        raise ValueError(f"{schema_path} contains duplicate {strategy_id!r} records")
    return _allocation_from_record(
        matches[0],
        strategy_id=strategy_id,
        allocation_fields=allocation_fields,
        schema_path=schema_path,
    )


def resolve_strategy_allocation(
    payload: Mapping[str, Any],
    strategy_id: str = STRATEGY_ID,
    *,
    allocation_fields: Sequence[str] = ALLOCATION_FIELDS,
) -> float:
    """Resolve authoritative strategy allocation from supported Enterprise schemas.

    Resolution order is deterministic:
    1. Authoritative AI CIO evidence ``payload.strategy_kpis[]`` record.
    2. Current registry ``strategy_plugins[]`` record.
    3. Legacy ``strategy_allocations[strategy_id]`` mapping.

    Stock-level ``portfolio_allocations.json`` data is intentionally unsupported.
    """
    evidence_payload = payload.get("payload")
    strategy_kpis = (
        evidence_payload.get("strategy_kpis")
        if isinstance(evidence_payload, Mapping)
        else None
    )
    allocated = _allocation_from_records(
        strategy_kpis,
        strategy_id=strategy_id,
        allocation_fields=allocation_fields,
        schema_path="payload.strategy_kpis",
    )
    if allocated is not None:
        return allocated

    allocated = _allocation_from_records(
        payload.get("strategy_plugins"),
        strategy_id=strategy_id,
        allocation_fields=allocation_fields,
        schema_path="strategy_plugins",
    )
    if allocated is not None:
        return allocated

    legacy = payload.get("strategy_allocations")
    if isinstance(legacy, Mapping):
        allocated = _finite_nonnegative(legacy.get(strategy_id))
        if allocated is None:
            raise ValueError(f"strategy_allocations[{strategy_id!r}] is required")
        return allocated

    raise ValueError(
        "Enterprise allocation evidence must contain payload.strategy_kpis, "
        "strategy_plugins, or strategy_allocations"
    )


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

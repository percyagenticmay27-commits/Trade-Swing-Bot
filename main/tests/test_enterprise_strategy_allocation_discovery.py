from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trade_bot.enterprise_strategy_allocation_discovery import (
    discover_strategy_allocations_file,
    load_discovered_strategy_allocations,
    resolve_strategy_allocation,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_legacy_strategy_allocations_schema() -> None:
    assert resolve_strategy_allocation(
        {"strategy_allocations": {"SWING-001": 1234.56}}
    ) == 1234.56


def test_current_strategy_plugins_registry_schema() -> None:
    payload = {
        "strategy_plugins": [
            {"strategy_id": "DIVIDEND-001", "allocated_capital": 9000},
            {"strategy_id": "SWING-001", "allocated_capital": 4321.0},
        ]
    }
    assert resolve_strategy_allocation(payload) == 4321.0


def test_ai_cio_strategy_evidence_schema() -> None:
    payload = {
        "payload": {
            "strategy_kpis": [
                {"strategy_id": "DIVIDEND-001", "allocated_capital": 5000.0},
                {"strategy_id": "SWING-001", "allocated_capital": 4500.0},
            ]
        }
    }
    assert resolve_strategy_allocation(payload) == 4500.0


def test_ai_cio_evidence_uses_exact_strategy_record() -> None:
    payload = {
        "payload": {
            "strategy_kpis": [
                {"strategy_id": "DIVIDEND-001", "allocated_capital": 9999.0},
                {"strategy_id": "SWING-001", "allocated_capital": 3210.75},
            ]
        },
        "historical_note": "SWING-001 previously had 4500.0",
    }
    assert resolve_strategy_allocation(payload) == 3210.75


def test_supported_current_allocation_field_variants() -> None:
    for field in (
        "allocated_capital",
        "allocation_amount",
        "capital_allocation",
        "strategy_allocation",
        "approved_capital",
    ):
        assert resolve_strategy_allocation(
            {"strategy_plugins": [{"strategy_id": "SWING-001", field: 101.25}]}
        ) == 101.25


def test_missing_swing_strategy_fails_clearly() -> None:
    with pytest.raises(ValueError, match="SWING-001"):
        resolve_strategy_allocation(
            {"strategy_plugins": [{"strategy_id": "DIVIDEND-001", "allocated_capital": 1}]}
        )


def test_missing_swing_in_ai_cio_evidence_fails_clearly() -> None:
    with pytest.raises(ValueError, match="payload.strategy_kpis.*SWING-001"):
        resolve_strategy_allocation(
            {
                "payload": {
                    "strategy_kpis": [
                        {"strategy_id": "DIVIDEND-001", "allocated_capital": 1}
                    ]
                }
            }
        )


def test_missing_allocation_value_fails_clearly() -> None:
    with pytest.raises(ValueError, match="supported allocation field"):
        resolve_strategy_allocation(
            {"strategy_plugins": [{"strategy_id": "SWING-001"}]}
        )


def test_missing_ai_cio_evidence_allocation_fails_clearly() -> None:
    with pytest.raises(ValueError, match="payload.strategy_kpis.*supported allocation field"):
        resolve_strategy_allocation(
            {"payload": {"strategy_kpis": [{"strategy_id": "SWING-001"}]}}
        )


def test_explicit_path_overrides_discovery(tmp_path: Path) -> None:
    explicit = _write(
        tmp_path / "explicit.json",
        {"strategy_allocations": {"SWING-001": 77}},
    )
    repository = tmp_path / "dividend"
    _write(
        repository / "results" / "enterprise_registry_strategy_evidence.json",
        {"payload": {"strategy_kpis": [{"strategy_id": "SWING-001", "allocated_capital": 88}]}},
    )
    assert discover_strategy_allocations_file(explicit, ai_cio_repository=repository) == explicit.resolve()


def test_discovers_direct_ai_cio_evidence_artifact(tmp_path: Path) -> None:
    repository = tmp_path / "Trade-Dividend-Bot"
    evidence = _write(
        repository / "results" / "enterprise_registry_strategy_evidence.json",
        {
            "payload": {
                "strategy_kpis": [
                    {"strategy_id": "SWING-001", "allocated_capital": 99}
                ]
            }
        },
    )
    payload, source = load_discovered_strategy_allocations(ai_cio_repository=repository)
    assert source == evidence.resolve()
    assert resolve_strategy_allocation(payload) == 99


def test_no_hard_coded_4500() -> None:
    assert resolve_strategy_allocation(
        {"payload": {"strategy_kpis": [{"strategy_id": "SWING-001", "allocated_capital": 3210.75}]}}
    ) == 3210.75


def test_stock_level_portfolio_allocations_are_not_enterprise_source() -> None:
    with pytest.raises(ValueError, match="payload.strategy_kpis"):
        resolve_strategy_allocation(
            {"allocations": [{"symbol": "SOXL", "allocation_amount": 2500}]}
        )


def test_external_evidence_path_cannot_escape_repository(tmp_path: Path) -> None:
    repository = tmp_path / "Trade-Dividend-Bot"
    repository.mkdir()
    with pytest.raises(ValueError, match="relative"):
        discover_strategy_allocations_file(
            ai_cio_repository=repository,
            registry_relative_path=tmp_path / "outside.json",
        )

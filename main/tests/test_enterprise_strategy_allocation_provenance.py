from __future__ import annotations

from swing_trade_bot.enterprise_strategy_allocation_discovery import (
    resolve_strategy_allocation,
    resolve_strategy_allocation_evidence,
)


def test_direct_ai_cio_evidence_reports_exact_json_path() -> None:
    payload = {
        "payload": {
            "strategy_kpis": [
                {"strategy_id": "DIVIDEND-001", "allocated_capital": 5000.0},
                {"strategy_id": "SWING-001", "allocated_capital": 4500.0},
            ]
        }
    }

    evidence = resolve_strategy_allocation_evidence(payload)

    assert evidence == {
        "allocated_capital": 4500.0,
        "allocation_evidence_schema": "payload.strategy_kpis",
        "allocation_source_json_path": "$.payload.strategy_kpis[1].allocated_capital",
        "allocation_field": "allocated_capital",
    }
    assert resolve_strategy_allocation(payload) == 4500.0


def test_nested_ai_cio_evidence_reports_shallowest_exact_json_path() -> None:
    payload = {
        "strategies": [
            {
                "artifacts": [
                    {
                        "payload": {
                            "strategy_kpis": [
                                {
                                    "strategy_id": "SWING-001",
                                    "allocated_capital": 3210.75,
                                }
                            ],
                            "historical": {
                                "strategy_kpis": [
                                    {
                                        "strategy_id": "SWING-001",
                                        "allocated_capital": 4500.0,
                                    }
                                ]
                            },
                        }
                    }
                ]
            }
        ]
    }

    evidence = resolve_strategy_allocation_evidence(payload)

    assert evidence["allocated_capital"] == 3210.75
    assert evidence["allocation_evidence_schema"] == "nested.payload.strategy_kpis"
    assert evidence["allocation_source_json_path"] == (
        "$.strategies[0].artifacts[0].payload.strategy_kpis[0].allocated_capital"
    )


def test_registry_and_legacy_provenance_remain_supported() -> None:
    registry = resolve_strategy_allocation_evidence(
        {
            "strategy_plugins": [
                {"strategy_id": "SWING-001", "approved_capital": 1250.0}
            ]
        }
    )
    legacy = resolve_strategy_allocation_evidence(
        {"strategy_allocations": {"SWING-001": 900.0}}
    )

    assert registry["allocation_evidence_schema"] == "strategy_plugins"
    assert registry["allocation_source_json_path"] == (
        "$.strategy_plugins[0].approved_capital"
    )
    assert legacy["allocation_evidence_schema"] == "strategy_allocations"
    assert legacy["allocation_source_json_path"] == (
        "$.strategy_allocations.SWING-001"
    )


def test_no_hard_coded_allocation_in_provenance_resolution() -> None:
    evidence = resolve_strategy_allocation_evidence(
        {
            "payload": {
                "strategy_kpis": [
                    {"strategy_id": "SWING-001", "allocated_capital": 2876.54}
                ]
            }
        }
    )

    assert evidence["allocated_capital"] == 2876.54

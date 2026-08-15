"""Command-line publisher for the Swing Enterprise KPI v2.1 evidence package."""
from __future__ import annotations

import argparse
from pathlib import Path

from swing_trade_bot.closed_trade_excursion_archive import (
    enrich_and_archive_closed_trade_excursions,
)
from swing_trade_bot.enterprise_strategy_allocation_discovery import (
    DEFAULT_AI_CIO_REGISTRY_RELATIVE_PATH,
    DEFAULT_AI_CIO_REPOSITORY,
    STRATEGY_ID,
    load_discovered_strategy_allocations,
    resolve_strategy_allocation_evidence,
)
from swing_trade_bot.enterprise_strategy_kpi_publisher_v21 import (
    build_enterprise_strategy_kpis_v21,
    write_enterprise_strategy_kpis_v21,
)
from swing_trade_bot.swing_trade_analytics_report import (
    build_swing_trade_analytics_report,
    write_swing_trade_analytics_report,
)
from swing_trade_bot.swing_strategy_alerts_report import (
    build_swing_strategy_alerts_report,
    write_swing_strategy_alerts_report,
)
from swing_trade_bot.swing_decision_journal_report import (
    build_swing_decision_journal_report,
    write_swing_decision_journal_report,
)


def publish(
    *,
    results_dir: str | Path = "results",
    output: str | Path = "results/enterprise_strategy_kpis.json",
    strategy_allocations_file: str | Path | None = None,
    ai_cio_repository: str | Path = DEFAULT_AI_CIO_REPOSITORY,
    ai_cio_registry_relative_path: str | Path = DEFAULT_AI_CIO_REGISTRY_RELATIVE_PATH,
) -> Path:
    """Discover authoritative AI CIO evidence and publish the Swing KPI artifact."""
    root = Path(results_dir)
    closed_positions = root / "paper_ledger/closed_positions.json"
    if closed_positions.is_file():
        enrich_and_archive_closed_trade_excursions(
            closed_positions_path=closed_positions,
            data_dir=root.resolve().parent / "data",
        )

    registry, allocation_path = load_discovered_strategy_allocations(
        strategy_allocations_file,
        ai_cio_repository=ai_cio_repository,
        registry_relative_path=ai_cio_registry_relative_path,
    )
    allocation_evidence = dict(
        resolve_strategy_allocation_evidence(registry, STRATEGY_ID)
    )
    allocated = float(allocation_evidence["allocated_capital"])

    # The existing KPI engine receives its validated compatibility shape. The
    # amount is resolved from authoritative AI CIO evidence and is never derived
    # from Swing stock-level portfolio_allocations.json.
    normalized = {"strategy_allocations": {STRATEGY_ID: allocated}}
    payload = build_enterprise_strategy_kpis_v21(
        results_dir,
        strategy_allocations=normalized,
        strategy_allocations_source=allocation_path,
    )

    # Replace the normalized compatibility provenance with the authoritative
    # external AI CIO provenance. Keep the top-level fields and nested object
    # synchronized from one source of truth so the write-time validator receives
    # the same allocation source in both locations.
    allocation_provenance = dict(allocation_evidence)
    allocation_provenance.update(
        {
            "allocated_capital": allocated,
            "allocation_source": "AI_CIO_ENTERPRISE_EVIDENCE",
            "allocation_source_path": str(allocation_path.resolve()),
        }
    )

    payload.update(
        {
            "allocated_capital": allocated,
            "allocation_source": allocation_provenance["allocation_source"],
            "allocation_source_path": allocation_provenance[
                "allocation_source_path"
            ],
            "allocation_source_json_path": allocation_provenance[
                "allocation_source_json_path"
            ],
            "allocation_evidence_schema": allocation_provenance[
                "allocation_evidence_schema"
            ],
            "allocation_field": allocation_provenance["allocation_field"],
            "allocation_provenance": allocation_provenance,
        }
    )

    # Keep every duplicated dashboard/portfolio provenance view synchronized.
    if isinstance(payload.get("portfolio"), dict):
        payload["portfolio"]["allocated_capital"] = allocated
        payload["portfolio"]["allocation_provenance"] = dict(
            allocation_provenance
        )
    if isinstance(payload.get("dashboard_sections"), dict):
        payload["dashboard_sections"]["allocation_provenance"] = dict(
            allocation_provenance
        )
        dashboard_portfolio = payload["dashboard_sections"].get("portfolio")
        if isinstance(dashboard_portfolio, dict):
            dashboard_portfolio["allocated_capital"] = allocated
            dashboard_portfolio["allocation_provenance"] = dict(
                allocation_provenance
            )

    payload["artifact_contract"] = sorted(
        payload["artifact_contract"], key=lambda row: row["artifact_id"]
    )
    trade_report = build_swing_trade_analytics_report(payload)
    write_swing_trade_analytics_report(trade_report, root)

    alerts_report = build_swing_strategy_alerts_report(
        root,
        kpi_payload=payload,
    )
    write_swing_strategy_alerts_report(alerts_report, root)
    payload["alerts"] = alerts_report
    if isinstance(payload.get("dashboard_sections"), dict):
        payload["dashboard_sections"]["alerts"] = alerts_report

    decision_journal = build_swing_decision_journal_report(
        root,
        kpi_payload=payload,
    )
    write_swing_decision_journal_report(decision_journal, root)
    payload["decision_journal"] = decision_journal
    if isinstance(payload.get("dashboard_sections"), dict):
        payload["dashboard_sections"]["decisions"] = decision_journal

    # The dedicated reports are created by this same atomic publication command.
    # Synchronize artifact availability before validating and writing the KPI
    # contract so consumers never receive a false missing-artifact warning.
    generated_artifact_ids = {
        "swing_trade_analytics_report",
        "swing_strategy_alerts_report",
        "swing_decision_journal_report",
    }
    for artifact in payload.get("artifact_contract", []):
        if artifact.get("artifact_id") in generated_artifact_ids:
            artifact["available"] = True
    available = set(payload.get("available_artifacts", []))
    available.update(generated_artifact_ids)
    missing = set(payload.get("missing_optional_artifacts", []))
    missing.difference_update(generated_artifact_ids)
    payload["available_artifacts"] = sorted(available)
    payload["missing_optional_artifacts"] = sorted(missing)
    payload["artifacts"] = len(available)
    warnings = [
        warning
        for warning in payload.get("warnings", [])
        if not str(warning).startswith("Optional evidence unavailable:")
    ]
    if missing:
        warnings.append("Optional evidence unavailable: " + ", ".join(sorted(missing)))
    payload["warnings"] = sorted(set(warnings))

    return write_enterprise_strategy_kpis_v21(payload, output)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish paper-only Swing Enterprise KPI v2.1 evidence."
    )
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--output", default="results/enterprise_strategy_kpis.json")
    parser.add_argument(
        "--strategy-allocations-file",
        default=None,
        help=(
            "Explicit authoritative allocation evidence. When omitted, discover "
            "the Dividend-hosted AI CIO strategy evidence artifact."
        ),
    )
    parser.add_argument(
        "--ai-cio-repository",
        default=str(DEFAULT_AI_CIO_REPOSITORY),
    )
    parser.add_argument(
        "--ai-cio-registry-relative-path",
        default=str(DEFAULT_AI_CIO_REGISTRY_RELATIVE_PATH),
    )
    args = parser.parse_args()

    output = publish(
        results_dir=args.results_dir,
        output=args.output,
        strategy_allocations_file=args.strategy_allocations_file,
        ai_cio_repository=args.ai_cio_repository,
        ai_cio_registry_relative_path=args.ai_cio_registry_relative_path,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line publisher for the Swing Enterprise KPI v2.1 evidence package."""
from __future__ import annotations

import argparse
from pathlib import Path

from swing_trade_bot.enterprise_strategy_allocation_discovery import (
    DEFAULT_AI_CIO_REGISTRY_RELATIVE_PATH,
    DEFAULT_AI_CIO_REPOSITORY,
    STRATEGY_ID,
    load_discovered_strategy_allocations,
    resolve_strategy_allocation,
)
from swing_trade_bot.enterprise_strategy_kpi_publisher_v21 import (
    build_enterprise_strategy_kpis_v21,
    write_enterprise_strategy_kpis_v21,
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
    registry, allocation_path = load_discovered_strategy_allocations(
        strategy_allocations_file,
        ai_cio_repository=ai_cio_repository,
        registry_relative_path=ai_cio_registry_relative_path,
    )
    allocated = resolve_strategy_allocation(registry, STRATEGY_ID)

    # The existing KPI engine remains unchanged and receives its validated legacy
    # input shape.  The value is resolved from authoritative AI CIO evidence; it
    # is never derived from Swing stock-level portfolio_allocations.json.
    normalized = {"strategy_allocations": {STRATEGY_ID: allocated}}
    payload = build_enterprise_strategy_kpis_v21(
        results_dir,
        strategy_allocations=normalized,
        strategy_allocations_source=allocation_path,
    )
    payload["allocation_evidence_schema"] = (
        "strategy_plugins" if isinstance(registry.get("strategy_plugins"), list)
        else "strategy_allocations"
    )
    payload["artifact_contract"] = sorted(
        payload["artifact_contract"], key=lambda row: row["artifact_id"]
    )
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
            "the Dividend-hosted AI CIO strategy registry."
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

"""Command-line publisher for the Swing Enterprise KPI v2.1 evidence package."""
from __future__ import annotations

import argparse
from pathlib import Path

from swing_trade_bot.enterprise_strategy_kpi_publisher_v21 import (
    _load_json,
    build_enterprise_strategy_kpis_v21,
    write_enterprise_strategy_kpis_v21,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish paper-only Swing Enterprise KPI v2.1 evidence.")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--output", default="results/enterprise_strategy_kpis.json")
    parser.add_argument(
        "--strategy-allocations-file",
        default="results/enterprise_strategy_allocations.json",
    )
    args = parser.parse_args()

    allocation_path = Path(args.strategy_allocations_file)
    allocations = _load_json(allocation_path)
    if allocations is None:
        raise FileNotFoundError(f"Strategy allocation evidence not found: {allocation_path}")

    payload = build_enterprise_strategy_kpis_v21(
        args.results_dir,
        strategy_allocations=allocations,
        strategy_allocations_source=allocation_path,
    )
    payload["artifact_contract"] = sorted(
        payload["artifact_contract"], key=lambda row: row["artifact_id"]
    )
    output = write_enterprise_strategy_kpis_v21(payload, args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

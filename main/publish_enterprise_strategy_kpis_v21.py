"""Command-line publisher for the Swing Enterprise KPI v2.1 evidence package."""
from __future__ import annotations

import argparse

from swing_trade_bot.enterprise_strategy_kpi_publisher_v21 import (
    build_and_write_enterprise_strategy_kpis_v21,
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

    output = build_and_write_enterprise_strategy_kpis_v21(
        args.results_dir,
        args.output,
        strategy_allocations_path=args.strategy_allocations_file,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

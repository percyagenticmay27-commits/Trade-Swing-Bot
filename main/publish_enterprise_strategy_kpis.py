"""Publish Swing paper-strategy KPI v2 evidence for the existing AI CIO host."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from swing_trade_bot.enterprise_strategy_kpi_publisher import (
    DEFAULT_STRATEGY_ALLOCATIONS_PATH,
    build_and_write_enterprise_strategy_kpis,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--output", default="results/enterprise_strategy_kpis.json")
    parser.add_argument(
        "--strategy-allocations-file",
        default=str(DEFAULT_STRATEGY_ALLOCATIONS_PATH),
        help="JSON containing strategy_allocations['SWING-001']; total account capital is not accepted.",
    )
    args = parser.parse_args()

    output = build_and_write_enterprise_strategy_kpis(
        args.results_dir,
        args.output,
        strategy_allocations_path=args.strategy_allocations_file,
    )
    payload = json.loads(Path(output).read_text(encoding="utf-8"))
    print(json.dumps({
        "output": str(output),
        "strategy_id": payload["strategy_id"],
        "kpi_contract_version": payload["kpi_contract_version"],
        "evidence_status": payload["evidence_status"],
        "allocated_capital": payload["allocated_capital"],
        "portfolio_value": payload["portfolio_value"],
        "portfolio_value_source": payload["portfolio_value_source"],
        "cash_balance": payload["cash_balance"],
        "invested_capital": payload["invested_capital"],
        "position_count": payload["position_count"],
        "trade_count": payload["trade_count"],
        "closed_trade_count": payload["closed_trade_count"],
        "win_rate_percent": payload["win_rate_percent"],
        "opportunity_quality": payload["opportunity_quality"],
        "watchlist_count": payload["watchlist_count"],
        "capabilities": payload["capabilities"],
        "artifacts": payload["artifacts"],
        "warnings": payload["warnings"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the shell-safe historical provider chain before portfolio valuation.

This runner uses YFINANCE -> STOOQ_READ_ONLY -> prior valid local CSV. Robinhood
MCP is intentionally not invented from a shell process; an authenticated Agentic
runtime may use build_configured_provider_chain(invoke_mcp=...) to include it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from swing_trade_bot.market_data_chain_factory import build_configured_provider_chain
from swing_trade_bot.market_data_refresh import (
    load_market_data_config,
    refresh_market_data,
    write_market_data_refresh_status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Swing daily bars through free providers")
    parser.add_argument("--config", type=Path, default=Path("configs/swing_market_data.json"))
    args = parser.parse_args()
    project_root = args.config.resolve().parent.parent
    config = load_market_data_config(args.config)
    provider = build_configured_provider_chain(
        config={"provider_order": ["YFINANCE", "STOOQ_READ_ONLY"]}
    )
    report = refresh_market_data(config, provider, project_root=project_root)
    write_market_data_refresh_status(report, project_root / "results")
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 1 if report.overall_status == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())

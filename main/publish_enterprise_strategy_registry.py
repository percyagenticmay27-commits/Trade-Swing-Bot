"""Validate and atomically publish the Swing Enterprise Registry v2 record."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from swing_trade_bot.swing_strategy_service_registration import (
    validate_strategy_service_registration,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/swing_strategy_service_registration.json")
    parser.add_argument("--output", default="results/swing_strategy_service_registration.json")
    args = parser.parse_args()

    source = Path(args.config)
    payload = json.loads(source.read_text(encoding="utf-8"))
    validation = validate_strategy_service_registration(payload)
    if not validation.valid:
        raise SystemExit("Invalid Swing Registry v2 metadata: " + "; ".join(validation.errors))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)

    print(json.dumps({
        "output": str(output),
        "strategy_id": payload["strategy_id"],
        "plugin_contract_version": payload["plugin_contract_version"],
        "capabilities": len(payload["capabilities"]),
        "artifacts": len(payload["dashboard_artifacts"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

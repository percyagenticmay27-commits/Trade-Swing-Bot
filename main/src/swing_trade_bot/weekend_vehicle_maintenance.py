"""Run the complete paper-only weekend leveraged-vehicle maintenance workflow."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from .weekend_vehicle_preference_persistence import (
    DEFAULT_LEGACY_MAPPING_PATH,
    DEFAULT_REGISTRY_PATH,
    apply_reviewed_preferences,
)
from .weekend_vehicle_review import (
    DEFAULT_OUTPUT_PATH,
    build_weekend_vehicle_review,
    write_weekend_vehicle_review,
)

DEFAULT_PERSISTENCE_REPORT_PATH = Path("results/weekend_vehicle_preference_persistence.json")


def _atomic_write(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


def run_weekend_vehicle_maintenance(
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    legacy_mapping_path: str | Path = DEFAULT_LEGACY_MAPPING_PATH,
    review_output_path: str | Path = DEFAULT_OUTPUT_PATH,
    persistence_report_path: str | Path = DEFAULT_PERSISTENCE_REPORT_PATH,
    reviewed_on: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Review vehicles and persist only the review-approved future preference map."""
    review = build_weekend_vehicle_review(
        registry_path=registry_path,
        reviewed_on=reviewed_on,
        force=force,
    )
    write_weekend_vehicle_review(review, review_output_path)
    persistence = apply_reviewed_preferences(
        review,
        registry_path=registry_path,
        legacy_mapping_path=legacy_mapping_path,
    )
    _atomic_write(Path(persistence_report_path), persistence)
    return {
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "reviewed_on": review.get("reviewed_on"),
        "verified_vehicle_evidence_count": review.get("verified_vehicle_evidence_count", 0),
        "unverified_vehicle_candidate_count": review.get("unverified_vehicle_candidate_count", 0),
        "preference_change_count": persistence["preference_change_count"],
        "selection_scope": "FUTURE_NEW_CANDIDATES_ONLY",
        "existing_positions_unchanged": True,
        "broker_execution_allowed": False,
        "order_placement_allowed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Swing weekend leveraged-vehicle maintenance")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--legacy-mapping", type=Path, default=DEFAULT_LEGACY_MAPPING_PATH)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--persistence-report", type=Path, default=DEFAULT_PERSISTENCE_REPORT_PATH)
    parser.add_argument("--reviewed-on", type=date.fromisoformat)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    result = run_weekend_vehicle_maintenance(
        registry_path=args.registry,
        legacy_mapping_path=args.legacy_mapping,
        review_output_path=args.review_output,
        persistence_report_path=args.persistence_report,
        reviewed_on=args.reviewed_on,
        force=args.force,
    )
    print(
        "weekend_vehicle_maintenance: "
        f"verified={result['verified_vehicle_evidence_count']} "
        f"unverified={result['unverified_vehicle_candidate_count']} "
        f"preference_changes={result['preference_change_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

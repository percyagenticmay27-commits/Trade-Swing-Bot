"""Weekend leveraged-vehicle evidence refresh for Swing discovery.

This module is research-only and paper-only. It refreshes tradability evidence for
already verified registry vehicles and may surface unverified search candidates for
later mapping verification. Search results never become mappings automatically and
never affect existing positions. Only verified registry vehicles may become the
preferred vehicle for future new Swing candidates.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .leveraged_vehicle_registry import (
    VehicleEvidence,
    build_weekly_review,
    load_vehicle_registry,
)

STRATEGY_ID = "SWING-001"
MODULE_VERSION = "1.0.0"
DEFAULT_REGISTRY_PATH = Path("configs/swing_leveraged_vehicle_registry.json")
DEFAULT_OUTPUT_PATH = Path("results/weekend_vehicle_review.json")
DEFAULT_DISCOVERY_LIMIT = 12
WEEKEND_DAYS = frozenset({5, 6})  # Saturday/Sunday


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_weekend(day: date) -> bool:
    return day.weekday() in WEEKEND_DAYS


def _float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _safe_info(ticker: Any) -> Mapping[str, Any]:
    try:
        info = ticker.get_info()
    except Exception:
        try:
            info = ticker.info
        except Exception:
            return {}
    return info if isinstance(info, Mapping) else {}


def _history(ticker: Any, *, period: str) -> Any:
    try:
        return ticker.history(period=period, auto_adjust=False)
    except TypeError:
        return ticker.history(period=period)


def collect_vehicle_evidence(
    underlying_symbol: str,
    vehicle_symbol: str,
    *,
    ticker_factory: Callable[[str], Any] | None = None,
) -> tuple[VehicleEvidence | None, list[str]]:
    """Collect market/product evidence for one already verified vehicle.

    Missing critical product facts produce a warning and exclude the row from
    preference scoring instead of inventing favorable zero values.
    """
    if ticker_factory is None:
        import yfinance as yf

        ticker_factory = yf.Ticker

    symbol = vehicle_symbol.strip().upper()
    underlying = underlying_symbol.strip().upper()
    ticker = ticker_factory(symbol)
    warnings: list[str] = []

    try:
        recent = _history(ticker, period="3mo")
        long_history = _history(ticker, period="max")
    except Exception as exc:
        return None, [f"MARKET_HISTORY_UNAVAILABLE:{symbol}:{exc}"]

    if getattr(recent, "empty", True):
        return None, [f"MARKET_HISTORY_EMPTY:{symbol}"]

    try:
        close = recent["Close"].dropna()
        volume = recent["Volume"].dropna()
        price = float(close.iloc[-1])
        average_volume = float(volume.tail(20).mean())
        aligned = recent.loc[close.index.intersection(volume.index)]
        average_dollar_volume = float((aligned["Close"] * aligned["Volume"]).tail(20).mean())
        history_days = int(len(long_history.index)) if not getattr(long_history, "empty", True) else int(len(recent.index))
    except Exception as exc:
        return None, [f"MARKET_HISTORY_MALFORMED:{symbol}:{exc}"]

    info = _safe_info(ticker)
    bid = _float(info.get("bid"))
    ask = _float(info.get("ask"))
    aum = _float(info.get("totalAssets"))
    expense = _float(
        info.get("netExpenseRatio", info.get("annualReportExpenseRatio", info.get("expenseRatio")))
    )

    missing: list[str] = []
    if bid is None or ask is None or bid <= 0 or ask < bid:
        missing.append("bid_ask")
    if aum is None:
        missing.append("aum")
    if expense is None:
        missing.append("expense_ratio")
    if missing:
        warnings.append(f"INCOMPLETE_PRODUCT_EVIDENCE:{symbol}:{','.join(missing)}")
        return None, warnings

    midpoint = (bid + ask) / 2.0
    spread_pct = ((ask - bid) / midpoint * 100.0) if midpoint > 0 else 0.0
    quote_type = str(info.get("quoteType", "")).strip().upper()
    product_active = quote_type in {"ETF", "MUTUALFUND", "EQUITY"} and price > 0

    return (
        VehicleEvidence(
            underlying_symbol=underlying,
            vehicle_symbol=symbol,
            price=price,
            average_daily_volume=max(average_volume, 0.0),
            average_daily_dollar_volume=max(average_dollar_volume, 0.0),
            bid_ask_spread_pct=max(spread_pct, 0.0),
            aum=aum,
            expense_ratio_pct=expense,
            history_days=max(history_days, 0),
            product_active=product_active,
        ),
        warnings,
    )


def discover_unverified_vehicle_candidates(
    underlying_symbol: str,
    *,
    search_factory: Callable[..., Any] | None = None,
    max_results: int = DEFAULT_DISCOVERY_LIMIT,
) -> list[dict[str, Any]]:
    """Surface possible related leveraged ETFs for human/issuer verification.

    Results are intentionally labeled UNVERIFIED and must never be merged into the
    persistent registry without an independent verification step.
    """
    if search_factory is None:
        import yfinance as yf

        search_factory = yf.Search

    underlying = underlying_symbol.strip().upper()
    queries = (
        f"2x long {underlying} ETF",
        f"leveraged {underlying} ETF",
    )
    found: dict[str, dict[str, Any]] = {}
    for query in queries:
        try:
            search = search_factory(query, max_results=max_results)
            quotes = getattr(search, "quotes", []) or []
        except Exception:
            continue
        for raw in quotes:
            if not isinstance(raw, Mapping):
                continue
            symbol = str(raw.get("symbol", "")).strip().upper()
            quote_type = str(raw.get("quoteType", "")).strip().upper()
            if not symbol or quote_type != "ETF":
                continue
            found.setdefault(
                symbol,
                {
                    "underlying_symbol": underlying,
                    "candidate_vehicle_symbol": symbol,
                    "short_name": raw.get("shortname") or raw.get("longname"),
                    "exchange": raw.get("exchange"),
                    "verification_status": "UNVERIFIED",
                    "source": "YFINANCE_SEARCH",
                    "search_query": query,
                },
            )
    return [found[symbol] for symbol in sorted(found)]


def build_weekend_vehicle_review(
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    reviewed_on: date | None = None,
    ticker_factory: Callable[[str], Any] | None = None,
    search_factory: Callable[..., Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    day = reviewed_on or date.today()
    if not force and not is_weekend(day):
        raise ValueError("weekend vehicle review may run only on Saturday/Sunday unless force=True")

    registry = load_vehicle_registry(registry_path)
    evidence: list[VehicleEvidence] = []
    warnings: list[str] = []
    candidate_queue: list[dict[str, Any]] = []

    for underlying in sorted(registry):
        entry = registry[underlying]
        for vehicle in entry.vehicles:
            if not vehicle.enabled or not vehicle.verified:
                continue
            row, row_warnings = collect_vehicle_evidence(
                underlying,
                vehicle.symbol,
                ticker_factory=ticker_factory,
            )
            warnings.extend(row_warnings)
            if row is not None:
                evidence.append(row)
        candidate_queue.extend(
            discover_unverified_vehicle_candidates(
                underlying,
                search_factory=search_factory,
            )
        )

    review = build_weekly_review(
        registry,
        evidence,
        reviewed_at=f"{day.isoformat()}T00:00:00Z",
    )
    registered = {
        vehicle.symbol
        for entry in registry.values()
        for vehicle in entry.vehicles
    }
    candidate_queue = [
        item for item in candidate_queue
        if item["candidate_vehicle_symbol"] not in registered
    ]
    review.update(
        {
            "module_version": MODULE_VERSION,
            "reviewed_on": day.isoformat(),
            "evidence_source": "YFINANCE_RESEARCH_DATA",
            "verified_vehicle_evidence": [asdict(row) for row in evidence],
            "verified_vehicle_evidence_count": len(evidence),
            "unverified_vehicle_candidates": candidate_queue,
            "unverified_vehicle_candidate_count": len(candidate_queue),
            "new_mapping_auto_registration_allowed": False,
            "mapping_verification_required": True,
            "warnings": warnings,
            "broker_execution_allowed": False,
            "order_placement_allowed": False,
            "existing_positions_unchanged": True,
        }
    )
    return review


def write_weekend_vehicle_review(payload: Mapping[str, Any], path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    temp.write_text(json.dumps(dict(payload), indent=2) + "\n", encoding="utf-8")
    temp.replace(destination)
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the paper-only Swing weekend leveraged-vehicle review")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--reviewed-on", type=date.fromisoformat)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    payload = build_weekend_vehicle_review(
        registry_path=args.registry,
        reviewed_on=args.reviewed_on,
        force=args.force,
    )
    write_weekend_vehicle_review(payload, args.output)
    print(
        f"weekend_vehicle_review: verified={payload['verified_vehicle_evidence_count']} "
        f"unverified={payload['unverified_vehicle_candidate_count']} "
        f"warnings={len(payload['warnings'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only SEC XBRL fundamental-data refresh for persistent Swing mappings.

The AI CIO nominates companies; Swing independently acquires filed company
fundamentals. This module retrieves raw SEC companyfacts data and derives the
metrics consumed by mapped_underlying_fundamental_evidence.py. It does not score
Opportunity Quality and does not use AI CIO discovery status.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .leveraged_vehicle_registry import preferred_vehicle_mapping

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
OUTPUT_NAME = "mapped_underlying_fundamental_data_refresh.json"

KNOWN_CIKS: dict[str, int] = {
    "AMZN": 1018724,
    "AVGO": 1730168,
    "GOOGL": 1652044,
    "NFLX": 1065280,
    "NVDA": 1045810,
    "PLTR": 1321655,
    "SNDK": 2023554,
}

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
NET_INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss")
OPERATING_INCOME_TAGS = ("OperatingIncomeLoss",)
CFO_TAGS = ("NetCashProvidedByUsedInOperatingActivities",)
CAPEX_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForAdditionsToPropertyPlantAndEquipment",
)
CURRENT_ASSET_TAGS = ("AssetsCurrent",)
CURRENT_LIABILITY_TAGS = ("LiabilitiesCurrent",)
EQUITY_TAGS = (
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
DEBT_COMBINED_TAGS = (
    "LongTermDebtAndFinanceLeaseObligations",
    "LongTermDebt",
)
DEBT_CURRENT_TAGS = (
    "LongTermDebtAndFinanceLeaseObligationsCurrent",
    "LongTermDebtCurrent",
)
DEBT_NONCURRENT_TAGS = (
    "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
    "LongTermDebtNoncurrent",
)

JsonFetcher = Callable[[str], Mapping[str, Any]]


def _declared_user_agent() -> str:
    value = os.getenv("SEC_USER_AGENT", "").strip()
    if not value or "@" not in value:
        raise RuntimeError(
            "SEC_USER_AGENT must identify Trade-Swing-Bot and include a contact email, "
            "for example: 'Trade-Swing-Bot admin@example.com'"
        )
    return value


def _fetch_json(url: str) -> Mapping[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": _declared_user_agent(),
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError(
                "SEC returned HTTP 403. Verify SEC_USER_AGENT contains a monitored "
                "contact email and that this host is within SEC fair-access limits."
            ) from exc
        raise
    if not isinstance(payload, Mapping):
        raise ValueError("SEC response must be a JSON object")
    return payload


def _ticker_to_cik(payload: Mapping[str, Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for item in payload.values():
        if not isinstance(item, Mapping):
            continue
        ticker = str(item.get("ticker", "")).strip().upper()
        cik = item.get("cik_str")
        if not ticker or cik is None:
            continue
        try:
            mapping[ticker] = int(cik)
        except (TypeError, ValueError):
            continue
    return mapping


def _resolve_ciks(symbols: list[str], fetch_json: JsonFetcher) -> dict[str, int]:
    result = {symbol: KNOWN_CIKS[symbol] for symbol in symbols if symbol in KNOWN_CIKS}
    unresolved = [symbol for symbol in symbols if symbol not in result]
    if unresolved:
        ticker_map = _ticker_to_cik(fetch_json(TICKER_MAP_URL))
        for symbol in unresolved:
            cik = ticker_map.get(symbol)
            if cik is not None:
                result[symbol] = cik
    return result


def _tag_annual_values(companyfacts: Mapping[str, Any], tag: str) -> list[tuple[str, float]]:
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    if not isinstance(us_gaap, Mapping):
        return []
    concept = us_gaap.get(tag)
    if not isinstance(concept, Mapping):
        return []
    units = concept.get("units")
    if not isinstance(units, Mapping):
        return []
    entries = units.get("USD")
    if not isinstance(entries, list):
        return []
    by_end: dict[str, tuple[str, float]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        form = str(entry.get("form", ""))
        fp = str(entry.get("fp", ""))
        end = str(entry.get("end", ""))
        filed = str(entry.get("filed", ""))
        if form not in {"10-K", "10-K/A"} or (fp and fp != "FY") or not end:
            continue
        try:
            value = float(entry.get("val"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        previous = by_end.get(end)
        if previous is None or filed >= previous[0]:
            by_end[end] = (filed, value)
    return [(end, by_end[end][1]) for end in sorted(by_end)]


def _annual_values(companyfacts: Mapping[str, Any], tags: tuple[str, ...]) -> list[tuple[str, float]]:
    """Choose the freshest viable concept series across alternative XBRL tags."""
    candidates = [_tag_annual_values(companyfacts, tag) for tag in tags]
    candidates = [values for values in candidates if values]
    if not candidates:
        return []
    return max(candidates, key=lambda values: (values[-1][0], len(values)))


def _value_for_end(companyfacts: Mapping[str, Any], tags: tuple[str, ...], end: str) -> float | None:
    for tag in tags:
        values = _tag_annual_values(companyfacts, tag)
        for value_end, value in reversed(values):
            if value_end == end:
                return value
    return None


def _growth_for_latest_common_series(values: list[tuple[str, float]]) -> float | None:
    if len(values) < 2:
        return None
    previous = values[-2][1]
    latest = values[-1][1]
    if previous == 0:
        return None
    return (latest - previous) / abs(previous) * 100.0


def _ratio(numerator: float | None, denominator: float | None, scale: float = 1.0) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * scale


def derive_fundamental_metrics(companyfacts: Mapping[str, Any]) -> dict[str, float]:
    revenue_values = _annual_values(companyfacts, REVENUE_TAGS)
    income_values = _annual_values(companyfacts, NET_INCOME_TAGS)
    if not revenue_values:
        return {}
    fiscal_end = revenue_values[-1][0]
    revenue = revenue_values[-1][1]
    net_income = _value_for_end(companyfacts, NET_INCOME_TAGS, fiscal_end)
    operating_income = _value_for_end(companyfacts, OPERATING_INCOME_TAGS, fiscal_end)
    cfo = _value_for_end(companyfacts, CFO_TAGS, fiscal_end)
    capex = _value_for_end(companyfacts, CAPEX_TAGS, fiscal_end)
    current_assets = _value_for_end(companyfacts, CURRENT_ASSET_TAGS, fiscal_end)
    current_liabilities = _value_for_end(companyfacts, CURRENT_LIABILITY_TAGS, fiscal_end)
    equity = _value_for_end(companyfacts, EQUITY_TAGS, fiscal_end)

    debt = _value_for_end(companyfacts, DEBT_COMBINED_TAGS, fiscal_end)
    if debt is None:
        debt_current = _value_for_end(companyfacts, DEBT_CURRENT_TAGS, fiscal_end)
        debt_noncurrent = _value_for_end(companyfacts, DEBT_NONCURRENT_TAGS, fiscal_end)
        if debt_current is not None or debt_noncurrent is not None:
            debt = (debt_current or 0.0) + (debt_noncurrent or 0.0)

    income_aligned = [(end, value) for end, value in income_values if end <= fiscal_end]
    raw: dict[str, float | None] = {
        "revenue_growth_pct": _growth_for_latest_common_series(revenue_values),
        "earnings_growth_pct": _growth_for_latest_common_series(income_aligned),
        "operating_margin_pct": _ratio(operating_income, revenue, 100.0),
        "free_cash_flow_margin_pct": _ratio(
            (cfo - capex) if cfo is not None and capex is not None else None,
            revenue,
            100.0,
        ),
        "return_on_equity_pct": _ratio(net_income, equity, 100.0),
        "current_ratio": _ratio(current_assets, current_liabilities),
        "debt_to_equity": _ratio(debt, equity),
    }
    result = {
        name: round(value, 6)
        for name, value in raw.items()
        if value is not None and math.isfinite(value)
    }
    result["fiscal_end"] = fiscal_end
    return result


def refresh_mapped_underlying_fundamental_data(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    fetch_json: JsonFetcher = _fetch_json,
) -> dict[str, Any]:
    mapping = preferred_vehicle_mapping(registry_path)
    symbols = sorted(mapping)
    cik_map = _resolve_ciks(symbols, fetch_json)
    rows: list[dict[str, Any]] = []
    usable = 0
    for symbol in symbols:
        cik = cik_map.get(symbol)
        if cik is None:
            rows.append({
                "underlying_symbol": symbol,
                "preferred_vehicle": mapping[symbol],
                "status": "CIK_NOT_FOUND",
                "metrics": {},
            })
            continue
        try:
            companyfacts = fetch_json(COMPANYFACTS_URL.format(cik=cik))
            metrics = derive_fundamental_metrics(companyfacts)
            status = "AVAILABLE" if metrics else "NO_USABLE_FUNDAMENTALS"
            if metrics:
                usable += 1
            rows.append({
                "underlying_symbol": symbol,
                "preferred_vehicle": mapping[symbol],
                "cik": f"{cik:010d}",
                "source": "SEC_EDGAR_COMPANYFACTS",
                "status": status,
                "metrics": metrics,
            })
        except Exception as exc:
            rows.append({
                "underlying_symbol": symbol,
                "preferred_vehicle": mapping[symbol],
                "cik": f"{cik:010d}",
                "source": "SEC_EDGAR_COMPANYFACTS",
                "status": "FETCH_OR_PARSE_ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "metrics": {},
            })
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "ai_cio_discovery_status_used_as_fundamental_data": False,
        "provider": "SEC_EDGAR_COMPANYFACTS",
        "mapped_underlying_count": len(mapping),
        "underlyings_with_fundamental_metrics": usable,
        "rows": rows,
    }


def write_mapped_underlying_fundamental_data(payload: Mapping[str, Any], *, output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / OUTPUT_NAME
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=root) as handle:
        json.dump(dict(payload), handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return path


def build_and_write_mapped_underlying_fundamental_data(
    *,
    registry_path: str | Path = "configs/swing_leveraged_vehicle_registry.json",
    output_dir: str | Path = "results",
    fetch_json: JsonFetcher = _fetch_json,
) -> dict[str, Any]:
    payload = refresh_mapped_underlying_fundamental_data(
        registry_path=registry_path,
        fetch_json=fetch_json,
    )
    write_mapped_underlying_fundamental_data(payload, output_dir=output_dir)
    return payload


if __name__ == "__main__":
    report = build_and_write_mapped_underlying_fundamental_data()
    print(
        "Mapped underlying fundamental data: "
        f"{report['underlyings_with_fundamental_metrics']}/{report['mapped_underlying_count']} with metrics"
    )

"""Server-ready, provider-isolated daily market-data refresh for paper trading."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .market_data_models import DailyMarketBar, MarketDataRefreshReport, SymbolRefreshResult, SymbolRequest
from .market_data_provider import MarketDataProvider, MarketDataProviderError
from .market_data_provider_chain import MarketDataProviderChain, ProviderChainResult
from .providers.robinhood_agent_provider import McpInvoker, RobinhoodAgentReadOnlyProvider
from .providers.yfinance_provider import YFinanceProvider

SCHEMA_VERSION = "1.0"
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-^]{0,14}$")
CSV_FIELDS = ("Date", "Open", "High", "Low", "Close", "Adj Close", "Volume")
LEGACY_REQUIRED_FIELDS = {"date", "close", "volume"}


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_market_data_provider_chain(invoke_mcp: McpInvoker) -> MarketDataProviderChain:
    """Build the approved read-only chain. The hosting runtime supplies MCP invocation."""
    return MarketDataProviderChain((YFinanceProvider(), RobinhoodAgentReadOnlyProvider(invoke_mcp)))


def load_market_data_config(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Market-data configuration root must be an object")
    return payload


def validate_market_data_config(payload: Mapping[str, Any]) -> ValidationResult:
    errors: list[str] = []
    if payload.get("market_data_schema_version") != SCHEMA_VERSION:
        errors.append("market_data_schema_version must be 1.0")
    if payload.get("provider") not in {"YFINANCE", "PROVIDER_CHAIN"}:
        errors.append("provider must be YFINANCE or PROVIDER_CHAIN")
    for field, expected in {
        "paper_trade_mode": True,
        "live_trading_enabled": False,
        "broker_execution_enabled": False,
        "order_placement_enabled": False,
        "ai_cio_market_data_owner": False,
    }.items():
        if payload.get(field, False if expected is False else None) is not expected:
            errors.append(f"{field} must be {str(expected).lower()}")
    minimum = payload.get("minimum_compatible_bars")
    target = payload.get("target_completed_bars")
    if not isinstance(minimum, int) or minimum < 51:
        errors.append("minimum_compatible_bars must be at least 51")
    if not isinstance(target, int) or target < 250:
        errors.append("target_completed_bars must be at least 250")
    if isinstance(minimum, int) and isinstance(target, int) and target < minimum:
        errors.append("target_completed_bars must not be below minimum_compatible_bars")
    for field in ("configured_strategy_symbols", "portfolio_symbols", "watchlist_symbols", "candidate_symbols"):
        if not isinstance(payload.get(field), list):
            errors.append(f"{field} must be a list")
    try:
        ZoneInfo(str(payload.get("exchange_timezone")))
    except Exception:
        errors.append("exchange_timezone must be a valid IANA timezone")
    try:
        time.fromisoformat(str(payload.get("market_close_time")))
    except ValueError:
        errors.append("market_close_time must use HH:MM format")
    buffer_minutes = payload.get("settlement_buffer_minutes")
    if not isinstance(buffer_minutes, int) or buffer_minutes < 0:
        errors.append("settlement_buffer_minutes must be a non-negative integer")
    freshness = payload.get("freshness")
    if not isinstance(freshness, Mapping):
        errors.append("freshness must be an object")
    else:
        warning = freshness.get("warning_after_completed_sessions")
        stale = freshness.get("stale_after_completed_sessions")
        if not isinstance(warning, int) or warning < 0:
            errors.append("freshness.warning_after_completed_sessions must be non-negative")
        if not isinstance(stale, int) or stale <= 0:
            errors.append("freshness.stale_after_completed_sessions must be positive")
        if isinstance(warning, int) and isinstance(stale, int) and stale <= warning:
            errors.append("freshness stale threshold must exceed warning threshold")
    try:
        resolve_symbol_requests(
            configured_strategy_symbols=payload.get("configured_strategy_symbols", []),
            portfolio_symbols=payload.get("portfolio_symbols", []),
            watchlist_symbols=payload.get("watchlist_symbols", []),
            candidate_symbols=payload.get("candidate_symbols", []),
        )
    except ValueError as exc:
        errors.append(str(exc))
    return ValidationResult(not errors, tuple(errors), ())


def resolve_symbol_requests(*, configured_strategy_symbols: Sequence[str], portfolio_symbols: Sequence[str], watchlist_symbols: Sequence[str], candidate_symbols: Sequence[str]) -> tuple[SymbolRequest, ...]:
    groups = (
        ("benchmark", True, ("SPY", "QQQ")),
        ("configured_strategy", True, configured_strategy_symbols),
        ("portfolio", True, portfolio_symbols),
        ("watchlist", False, watchlist_symbols),
        ("candidate", False, candidate_symbols),
    )
    order: list[str] = []
    required: dict[str, bool] = {}
    sources: dict[str, list[str]] = {}
    for source, is_required, values in groups:
        for raw in values:
            symbol = str(raw).strip().upper()
            if not symbol or not SYMBOL_RE.fullmatch(symbol):
                raise ValueError(f"Invalid market-data symbol: {raw!r}")
            if symbol not in required:
                order.append(symbol)
                required[symbol] = is_required
                sources[symbol] = []
            required[symbol] = required[symbol] or is_required
            if source not in sources[symbol]:
                sources[symbol].append(source)
    return tuple(SymbolRequest(symbol, required[symbol], tuple(sources[symbol])) for symbol in order)


def normalize_daily_bars(bars: Iterable[DailyMarketBar], *, as_of_utc: datetime, exchange_timezone: str, market_close_time: time, settlement_buffer_minutes: int) -> tuple[DailyMarketBar, ...]:
    by_date: dict[date, DailyMarketBar] = {}
    local_now = as_of_utc.astimezone(ZoneInfo(exchange_timezone))
    cutoff = datetime.combine(local_now.date(), market_close_time, tzinfo=local_now.tzinfo) + timedelta(minutes=settlement_buffer_minutes)
    today_complete = local_now >= cutoff
    for bar in bars:
        errors = bar.validate()
        if errors:
            raise ValueError(f"Invalid bar {bar.date}: {'; '.join(errors)}")
        if bar.date > local_now.date() or (bar.date == local_now.date() and not today_complete):
            continue
        previous = by_date.get(bar.date)
        if previous is not None and previous != bar:
            raise ValueError(f"Conflicting duplicate bars for {bar.date}")
        by_date[bar.date] = bar
    return tuple(by_date[key] for key in sorted(by_date))


def validate_bar_set(bars: Sequence[DailyMarketBar], *, minimum_compatible_bars: int, target_completed_bars: int) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if any(left.date >= right.date for left, right in zip(bars, bars[1:])):
        errors.append("bars must be strictly chronological with no duplicate dates")
    for bar in bars:
        bar_errors = bar.validate()
        if bar_errors:
            errors.append(f"invalid bar {bar.date}: {'; '.join(bar_errors)}")
    if len(bars) < minimum_compatible_bars:
        errors.append(f"only {len(bars)} completed bars; at least {minimum_compatible_bars} required")
    elif len(bars) < target_completed_bars:
        warnings.append(f"only {len(bars)} completed bars; target is {target_completed_bars}")
    return ValidationResult(not errors, tuple(errors), tuple(warnings))


def render_market_data_csv(bars: Sequence[DailyMarketBar]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for bar in bars:
        writer.writerow({"Date": bar.date.isoformat(), "Open": str(bar.open), "High": str(bar.high), "Low": str(bar.low), "Close": str(bar.close), "Adj Close": str(bar.adjusted_close), "Volume": str(bar.volume)})
    return stream.getvalue()


def _normalized_header_map(fieldnames: Sequence[str] | None) -> dict[str, str]:
    if fieldnames is None:
        raise ValueError("CSV is missing a header row")
    mapping: dict[str, str] = {}
    for original in fieldnames:
        normalized = " ".join(str(original).strip().lower().replace("_", " ").split())
        if normalized in mapping:
            raise ValueError(f"CSV contains duplicate normalized header: {normalized}")
        mapping[normalized] = original
    return mapping


def _decimal_value(row: Mapping[str, str], header_map: Mapping[str, str], name: str, *, fallback: Decimal | None = None) -> Decimal:
    original = header_map.get(name)
    if original is None:
        if fallback is None:
            raise ValueError(f"CSV is missing required numeric column: {name}")
        return fallback
    raw = str(row.get(original, "")).strip()
    if not raw:
        if fallback is None:
            raise ValueError(f"CSV contains blank numeric value for: {name}")
        return fallback
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"CSV contains invalid numeric value for {name}: {raw!r}") from exc


def read_market_data_csv(path: str | Path, *, allow_legacy: bool = False) -> tuple[DailyMarketBar, ...]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not allow_legacy:
            if reader.fieldnames != list(CSV_FIELDS):
                raise ValueError(f"CSV header must be {','.join(CSV_FIELDS)}")
            header_map = {name.lower(): name for name in CSV_FIELDS}
        else:
            header_map = _normalized_header_map(reader.fieldnames)
            missing = sorted(LEGACY_REQUIRED_FIELDS - set(header_map))
            if missing:
                raise ValueError("legacy CSV must contain date, close, and volume columns; missing: " + ", ".join(missing))
        bars: list[DailyMarketBar] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                close = _decimal_value(row, header_map, "close")
                open_price = _decimal_value(row, header_map, "open", fallback=close)
                high = _decimal_value(row, header_map, "high", fallback=max(open_price, close))
                low = _decimal_value(row, header_map, "low", fallback=min(open_price, close))
                adjusted = _decimal_value(row, header_map, "adj close", fallback=_decimal_value(row, header_map, "adjusted close", fallback=close))
                volume_raw = str(row.get(header_map["volume"], "")).strip()
                if not volume_raw:
                    raise ValueError("blank volume")
                bar = DailyMarketBar(
                    date=date.fromisoformat(str(row.get(header_map["date"], "")).strip()),
                    open=open_price, high=high, low=low, close=close,
                    adjusted_close=adjusted, volume=int(Decimal(volume_raw)),
                )
                bar_errors = bar.validate()
                if bar_errors:
                    raise ValueError("; ".join(bar_errors))
                bars.append(bar)
            except (KeyError, ValueError, InvalidOperation) as exc:
                raise ValueError(f"invalid CSV row {row_number}: {exc}") from exc
        return tuple(bars)


def atomic_write_market_data_csv(bars: Sequence[DailyMarketBar], destination: str | Path, *, minimum_bars: int) -> Path:
    final_path = Path(destination)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = final_path.with_name(final_path.name + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(render_market_data_csv(bars)); handle.flush(); os.fsync(handle.fileno())
        reread = read_market_data_csv(temp_path, allow_legacy=False)
        validation = validate_bar_set(reread, minimum_compatible_bars=minimum_bars, target_completed_bars=minimum_bars)
        if not validation.valid:
            raise ValueError("temporary CSV validation failed: " + "; ".join(validation.errors))
        os.replace(temp_path, final_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return final_path


def _expected_latest_date(as_of_utc: datetime, tz_name: str, close_time: time, buffer_minutes: int) -> date:
    local = as_of_utc.astimezone(ZoneInfo(tz_name))
    cutoff = datetime.combine(local.date(), close_time, tzinfo=local.tzinfo) + timedelta(minutes=buffer_minutes)
    candidate = local.date() if local >= cutoff else local.date() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _business_day_lag(latest: date, expected: date) -> int:
    if latest >= expected:
        return 0
    count = 0; current = latest
    while current < expected:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return count


def _freshness(latest: date | None, config: Mapping[str, Any], as_of_utc: datetime) -> str:
    if latest is None:
        return "MISSING"
    expected = _expected_latest_date(as_of_utc, str(config["exchange_timezone"]), time.fromisoformat(str(config["market_close_time"])), int(config["settlement_buffer_minutes"]))
    lag = _business_day_lag(latest, expected)
    freshness = config["freshness"]
    if lag >= int(freshness["stale_after_completed_sessions"]):
        return "STALE"
    if lag >= int(freshness["warning_after_completed_sessions"]):
        return "WARNING"
    return "FRESH"


def refresh_symbol(provider: MarketDataProvider, request: SymbolRequest, *, data_directory: str | Path, config: Mapping[str, Any], as_of_utc: datetime) -> SymbolRefreshResult:
    destination = Path(data_directory) / f"{request.symbol}.csv"
    warnings: list[str] = []; errors: list[str] = []
    fetch_status = "FAILED"; validation_status = "NOT_RUN"; publication_status = "NOT_PUBLISHED"
    bars: tuple[DailyMarketBar, ...] = (); provider_attempts: tuple[dict[str, Any], ...] = ()
    selected_provider: str | None = None; adjusted_close_source = "UNAVAILABLE"; corporate_action_adjusted = False
    try:
        fetched = provider.fetch_daily_bars(request.symbol, target_completed_bars=int(config["target_completed_bars"]), as_of_utc=as_of_utc)
        if isinstance(fetched, ProviderChainResult):
            provider_attempts = tuple(item.to_dict() for item in fetched.attempts)
            if not fetched.bars:
                raise MarketDataProviderError("all configured providers failed")
            bars = fetched.bars; selected_provider = fetched.selected_provider
            adjusted_close_source = fetched.adjusted_close_source
            corporate_action_adjusted = fetched.corporate_action_adjusted
        else:
            bars = tuple(fetched); selected_provider = provider.provider_name
            provider_attempts = ({"provider": provider.provider_name, "status": "SUCCESS", "error": None, "classification": None, "bar_count": len(bars)},)
            adjusted_close_source = str(getattr(provider, "adjusted_close_source", "PROVIDER_ADJUSTED_CLOSE"))
            corporate_action_adjusted = bool(getattr(provider, "corporate_action_adjusted", True))
        fetch_status = "SUCCESS"
        bars = normalize_daily_bars(bars, as_of_utc=as_of_utc, exchange_timezone=str(config["exchange_timezone"]), market_close_time=time.fromisoformat(str(config["market_close_time"])), settlement_buffer_minutes=int(config["settlement_buffer_minutes"]))
        result = validate_bar_set(bars, minimum_compatible_bars=int(config["minimum_compatible_bars"]), target_completed_bars=int(config["target_completed_bars"]))
        warnings.extend(result.warnings)
        if not result.valid:
            validation_status = "FAILED"; errors.extend(result.errors); raise ValueError("; ".join(result.errors))
        validation_status = "PASSED"
        atomic_write_market_data_csv(bars, destination, minimum_bars=int(config["minimum_compatible_bars"]))
        publication_status = "PUBLISHED"
    except (MarketDataProviderError, ValueError, OSError) as exc:
        errors.append(str(exc))
        if not provider_attempts:
            provider_attempts = ({"provider": provider.provider_name, "status": "FAILED", "error": str(exc), "classification": getattr(exc, "classification", None), "bar_count": 0},)
        if destination.exists():
            try:
                prior = normalize_daily_bars(read_market_data_csv(destination, allow_legacy=True), as_of_utc=as_of_utc, exchange_timezone=str(config["exchange_timezone"]), market_close_time=time.fromisoformat(str(config["market_close_time"])), settlement_buffer_minutes=int(config["settlement_buffer_minutes"]))
                prior_validation = validate_bar_set(prior, minimum_compatible_bars=int(config["minimum_compatible_bars"]), target_completed_bars=int(config["target_completed_bars"]))
                prior_freshness = _freshness(prior[-1].date if prior else None, config, as_of_utc)
                if prior_validation.valid and prior_freshness in {"FRESH", "WARNING"}:
                    bars = prior; validation_status = "PRIOR_VALID"; publication_status = "PRESERVED_PRIOR_VALID_FILE"
                    selected_provider = "PRIOR_LOCAL_CSV"; adjusted_close_source = "PRIOR_FILE"
                    corporate_action_adjusted = False
                    provider_attempts += ({"provider": "PRIOR_LOCAL_CSV", "status": "SUCCESS", "error": None, "classification": None, "bar_count": len(prior)},)
                    warnings.extend(prior_validation.warnings); warnings.append("provider chain failed; preserved prior valid file"); errors = []
                else:
                    provider_attempts += ({"provider": "PRIOR_LOCAL_CSV", "status": "FAILED", "error": "stale or invalid prior file", "classification": "INSUFFICIENT_HISTORY" if not prior_validation.valid else "NETWORK_FAILURE", "bar_count": len(prior)},)
                    if prior_freshness == "STALE": errors.append("prior file is structurally valid but stale")
                    else: errors.extend(f"prior file validation failed: {item}" for item in prior_validation.errors)
            except (ValueError, OSError, IndexError) as prior_exc:
                provider_attempts += ({"provider": "PRIOR_LOCAL_CSV", "status": "FAILED", "error": str(prior_exc), "classification": "PROVIDER_SCHEMA_ERROR", "bar_count": 0},)
                errors.append(f"prior file is unusable: {prior_exc}")
    latest = bars[-1].date if bars else None
    freshness_status = _freshness(latest, config, as_of_utc)
    usable = publication_status in {"PUBLISHED", "PRESERVED_PRIOR_VALID_FILE"} and freshness_status in {"FRESH", "WARNING"}
    return SymbolRefreshResult(
        symbol=request.symbol, required=request.required, fetch_status=fetch_status,
        validation_status=validation_status, publication_status=publication_status,
        output_path=str(destination), bar_count=len(bars),
        latest_completed_date=latest.isoformat() if latest else None,
        freshness_status=freshness_status,
        prior_file_preserved=publication_status == "PRESERVED_PRIOR_VALID_FILE",
        provider_attempts=provider_attempts, selected_provider=selected_provider,
        adjusted_close_source=adjusted_close_source,
        corporate_action_adjusted=corporate_action_adjusted,
        warnings=tuple(dict.fromkeys(warnings)),
        errors=() if usable else tuple(dict.fromkeys(errors or ["symbol data is not usable"])),
    )


def refresh_market_data(config: Mapping[str, Any], provider: MarketDataProvider, *, project_root: str | Path, as_of_utc: datetime | None = None) -> MarketDataRefreshReport:
    now = as_of_utc or _utc_now(); config_validation = validate_market_data_config(config)
    if not config_validation.valid:
        return MarketDataRefreshReport(generated_at=_iso_utc(now), provider=str(config.get("provider", "UNKNOWN")), requested_symbols=(), required_symbols=(), optional_symbols=(), successful_symbols=(), failed_symbols=(), target_completed_bars=int(config.get("target_completed_bars", 0) or 0), minimum_compatible_bars=int(config.get("minimum_compatible_bars", 0) or 0), symbol_results=(), overall_status="BLOCKED", warnings=(), errors=config_validation.errors)
    requests = resolve_symbol_requests(configured_strategy_symbols=config["configured_strategy_symbols"], portfolio_symbols=config["portfolio_symbols"], watchlist_symbols=config["watchlist_symbols"], candidate_symbols=config["candidate_symbols"])
    data_dir = Path(project_root) / str(config["data_directory"])
    results = tuple(refresh_symbol(provider, item, data_directory=data_dir, config=config, as_of_utc=now) for item in requests)
    successful = tuple(item.symbol for item in results if not item.errors); failed = tuple(item.symbol for item in results if item.errors)
    required_failures = [item for item in results if item.required and item.errors]; optional_failures = [item for item in results if not item.required and item.errors]
    warnings = [warning for item in results for warning in item.warnings]
    errors = [f"{item.symbol}: {error}" for item in required_failures for error in item.errors]
    overall = "BLOCKED" if required_failures else ("READY_WITH_WARNINGS" if optional_failures or warnings else "READY")
    return MarketDataRefreshReport(generated_at=_iso_utc(now), provider=provider.provider_name, requested_symbols=tuple(item.symbol for item in requests), required_symbols=tuple(item.symbol for item in requests if item.required), optional_symbols=tuple(item.symbol for item in requests if not item.required), successful_symbols=successful, failed_symbols=failed, target_completed_bars=int(config["target_completed_bars"]), minimum_compatible_bars=int(config["minimum_compatible_bars"]), symbol_results=results, overall_status=overall, warnings=tuple(dict.fromkeys(warnings + [f"{item.symbol}: optional symbol failed" for item in optional_failures])), errors=tuple(dict.fromkeys(errors)))


def render_markdown(report: MarketDataRefreshReport) -> str:
    lines = ["# Market Data Refresh Status", "", f"- Generated at: `{report.generated_at}`", f"- Provider chain: `{report.provider}`", f"- Overall status: **{report.overall_status}**", f"- Requested: {len(report.requested_symbols)}", f"- Successful: {len(report.successful_symbols)}", f"- Failed: {len(report.failed_symbols)}", "", "## Symbol Results", "", "| Symbol | Selected Provider | Fetch | Validation | Publication | Bars | Latest | Freshness | Adj Close Source |", "|---|---|---|---|---|---:|---|---|---|"]
    for item in report.symbol_results:
        lines.append(f"| {item.symbol} | {item.selected_provider or ''} | {item.fetch_status} | {item.validation_status} | {item.publication_status} | {item.bar_count} | {item.latest_completed_date or ''} | {item.freshness_status} | {item.adjusted_close_source} |")
    lines.extend(["", "## Warnings", ""]); lines.extend(f"- {item}" for item in report.warnings) if report.warnings else lines.append("- None")
    lines.extend(["", "## Errors", ""]); lines.extend(f"- {item}" for item in report.errors) if report.errors else lines.append("- None")
    lines.extend(["", "Paper-only market-data refresh. No brokerage execution, order placement, or AI CIO data ownership.", ""])
    return "\n".join(lines)


def _atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists(): temp.unlink()


def write_market_data_refresh_status(report: MarketDataRefreshReport, output_directory: str | Path) -> dict[str, str]:
    output = Path(output_directory); json_path = output / "market_data_refresh_status.json"; md_path = output / "market_data_refresh_status.md"
    _atomic_write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", json_path); _atomic_write_text(render_markdown(report), md_path)
    return {"json": str(json_path), "markdown": str(md_path)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh completed daily market data for the paper Swing Bot")
    parser.add_argument("--config", type=Path, required=True); args = parser.parse_args(argv); project_root = args.config.resolve().parent.parent
    try:
        config = load_market_data_config(args.config)
        if config.get("provider") == "PROVIDER_CHAIN":
            raise RuntimeError("PROVIDER_CHAIN requires the hosting Agentic runtime to inject the connected MCP invoker through build_market_data_provider_chain()")
        report = refresh_market_data(config, YFinanceProvider(), project_root=project_root)
    except Exception as exc:
        now = _utc_now(); report = MarketDataRefreshReport(generated_at=_iso_utc(now), provider="YFINANCE", requested_symbols=(), required_symbols=(), optional_symbols=(), successful_symbols=(), failed_symbols=(), target_completed_bars=250, minimum_compatible_bars=51, symbol_results=(), overall_status="BLOCKED", warnings=(), errors=(str(exc),))
    write_market_data_refresh_status(report, project_root / "results"); print(json.dumps(report.to_dict(), indent=2, sort_keys=True)); return 1 if report.overall_status == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())

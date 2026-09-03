"""Read-only six-gate Discovery/Watchlist promotion readiness evaluation.

Promotion readiness is advisory and paper-only. It never changes lifecycle state,
assigns a strategy, allocates capital, places an order, or creates a position.
"""
from __future__ import annotations
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence
GateStatus = Literal["PASS", "FAIL", "PENDING"]
SOURCE_CONFLUENCE_MIN=5.0
FINANCIAL_HEALTH_MIN=70.0
THEME_MOMENTUM_MIN=70.0
OPPORTUNITY_QUALITY_MIN=70.0
ENTRY_SCORE_MIN=70.0
@dataclass(frozen=True, slots=True)
class GateResult:
    status: GateStatus
    value: float | bool | None
    threshold: float | bool
    reason: str
    evidence_source: str
@dataclass(frozen=True, slots=True)
class PromotionReadinessResult:
    underlying_symbol: str
    leveraged_symbol: str
    lifecycle_status: str
    trusted_sources: GateResult
    financial_health: GateResult
    theme_strength: GateResult
    opportunity_quality: GateResult
    thesis_integrity: GateResult
    entry: GateResult
    promotion_ready: bool
    blocking_reasons: tuple[str, ...]
def numeric_gate(value: float|int|None, threshold: float, *, name: str, evidence_source: str, stale: bool=False) -> GateResult:
    if stale: return GateResult("PENDING",None,threshold,f"{name} evidence is stale",evidence_source)
    if value is None: return GateResult("PENDING",None,threshold,f"{name} evidence is unavailable",evidence_source)
    actual=float(value); status: GateStatus="PASS" if actual>=threshold else "FAIL"
    return GateResult(status,actual,threshold,f"{name} {actual:g} {'meets' if status=='PASS' else 'is below'} threshold {threshold:g}",evidence_source)
def thesis_gate(value: bool|None, *, evidence_source: str, stale: bool=False) -> GateResult:
    if stale: return GateResult("PENDING",None,True,"Thesis evidence is stale",evidence_source)
    if value is None: return GateResult("PENDING",None,True,"Thesis evidence is unavailable",evidence_source)
    return GateResult("PASS" if value is True else "FAIL",value,True,"Thesis is intact" if value is True else "Thesis is not intact",evidence_source)
def evaluate_promotion_readiness(*, underlying_symbol: str, leveraged_symbol: str="", lifecycle_status: str, source_confluence_score: float|int|None, financial_health_score: float|int|None, theme_momentum_score: float|int|None, opportunity_quality_score: float|int|None, thesis_intact: bool|None, entry_score: float|int|None, stale: Mapping[str,bool]|None=None, evidence_sources: Mapping[str,str]|None=None) -> PromotionReadinessResult:
    stale=stale or {}; sources=evidence_sources or {}
    gates={"trusted_sources":numeric_gate(source_confluence_score,SOURCE_CONFLUENCE_MIN,name="Source Confluence",evidence_source=sources.get("trusted_sources","watchlist_report.json"),stale=bool(stale.get("trusted_sources"))),"financial_health":numeric_gate(financial_health_score,FINANCIAL_HEALTH_MIN,name="Financial Health",evidence_source=sources.get("financial_health","financial_health"),stale=bool(stale.get("financial_health"))),"theme_strength":numeric_gate(theme_momentum_score,THEME_MOMENTUM_MIN,name="Theme Momentum",evidence_source=sources.get("theme_strength","watchlist_report.json"),stale=bool(stale.get("theme_strength"))),"opportunity_quality":numeric_gate(opportunity_quality_score,OPPORTUNITY_QUALITY_MIN,name="Opportunity Quality",evidence_source=sources.get("opportunity_quality","opportunity_quality_report.json"),stale=bool(stale.get("opportunity_quality"))),"thesis_integrity":thesis_gate(thesis_intact,evidence_source=sources.get("thesis_integrity","thesis_monitor_v2_report.json"),stale=bool(stale.get("thesis_integrity"))),"entry":numeric_gate(entry_score,ENTRY_SCORE_MIN,name="Entry Score",evidence_source=sources.get("entry","entry_score_report.json"),stale=bool(stale.get("entry")))}
    lifecycle=lifecycle_status.strip().upper(); blocking=[f"{name}: {gate.reason}" for name,gate in gates.items() if gate.status!="PASS"]
    if lifecycle!="WATCHLIST": blocking.insert(0,f"lifecycle_status: {lifecycle or 'UNKNOWN'} is not WATCHLIST")
    ready=lifecycle=="WATCHLIST" and all(gate.status=="PASS" for gate in gates.values())
    return PromotionReadinessResult(underlying_symbol=underlying_symbol.strip().upper(),leveraged_symbol=leveraged_symbol.strip().upper(),lifecycle_status=lifecycle,promotion_ready=ready,blocking_reasons=tuple(blocking),**gates)
def build_report(results: Sequence[PromotionReadinessResult]) -> dict[str,Any]:
    return {"schema_version":"1.0","paper_trade_mode":True,"advisory_only":True,"automatic_lifecycle_change":False,"allocation_side_effects":False,"trade_side_effects":False,"thresholds":{"source_confluence_score":SOURCE_CONFLUENCE_MIN,"financial_health_score":FINANCIAL_HEALTH_MIN,"theme_momentum_score":THEME_MOMENTUM_MIN,"opportunity_quality_score":OPPORTUNITY_QUALITY_MIN,"thesis_intact":True,"entry_score":ENTRY_SCORE_MIN},"results":[asdict(item) for item in results]}
def write_reports(output_dir: str|Path, results: Sequence[PromotionReadinessResult]) -> tuple[Path,Path]:
    output=Path(output_dir); output.mkdir(parents=True,exist_ok=True); json_path=output/"promotion_readiness_report.json"; csv_path=output/"promotion_readiness_report.csv"; json_path.write_text(json.dumps(build_report(results),indent=2)+"\n",encoding="utf-8")
    fields=["underlying_symbol","leveraged_symbol","lifecycle_status","promotion_ready","trusted_sources_status","trusted_sources_value","financial_health_status","financial_health_value","theme_strength_status","theme_strength_value","opportunity_quality_status","opportunity_quality_value","thesis_integrity_status","thesis_integrity_value","entry_status","entry_value","blocking_reasons"]
    with csv_path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader()
        for item in results: writer.writerow({"underlying_symbol":item.underlying_symbol,"leveraged_symbol":item.leveraged_symbol,"lifecycle_status":item.lifecycle_status,"promotion_ready":item.promotion_ready,"trusted_sources_status":item.trusted_sources.status,"trusted_sources_value":item.trusted_sources.value,"financial_health_status":item.financial_health.status,"financial_health_value":item.financial_health.value,"theme_strength_status":item.theme_strength.status,"theme_strength_value":item.theme_strength.value,"opportunity_quality_status":item.opportunity_quality.status,"opportunity_quality_value":item.opportunity_quality.value,"thesis_integrity_status":item.thesis_integrity.status,"thesis_integrity_value":item.thesis_integrity.value,"entry_status":item.entry.status,"entry_value":item.entry.value,"blocking_reasons":" | ".join(item.blocking_reasons)})
    return json_path,csv_path

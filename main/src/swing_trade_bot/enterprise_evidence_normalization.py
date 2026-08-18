"""Deterministic AI CIO discovery-source normalization for SWING-001.

This adapter classifies Enterprise discovery evidence before it reaches the existing
Swing confluence engine. Legacy Swing source strings are not reclassified here.
Unknown or malformed Enterprise sources never receive trusted-source weight.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceClassProfile:
    weight: int
    institutional: bool = False
    youtube_or_creator: bool = False


@dataclass(frozen=True, slots=True)
class NormalizedEnterpriseSource:
    original_source: str
    source_class: str | None
    accepted: bool
    normalization_method: str
    warning: str | None = None


SOURCE_CLASS_PROFILES: dict[str, SourceClassProfile] = {
    "PRIMARY_REGULATORY": SourceClassProfile(3, institutional=True),
    "COMPANY_PRIMARY": SourceClassProfile(3, institutional=True),
    "INSTITUTIONAL_NEWS": SourceClassProfile(3, institutional=True),
    "PROFESSIONAL_RESEARCH": SourceClassProfile(2, institutional=True),
    "PROFESSIONAL_CREATOR": SourceClassProfile(1, youtube_or_creator=True),
    "MARKET_ANALYTICS": SourceClassProfile(1),
    "SOCIAL_COMMUNITY": SourceClassProfile(0),
}

# Accept normalized vocabulary variants the AI CIO may publish without changing
# Swing's scoring semantics. All aliases resolve to one of the approved classes.
SOURCE_CLASS_ALIASES: dict[str, str] = {
    "PRIMARY_REGULATORY": "PRIMARY_REGULATORY",
    "PRIMARY_REGULATORY_EVIDENCE": "PRIMARY_REGULATORY",
    "REGULATORY_PRIMARY": "PRIMARY_REGULATORY",
    "SEC_REGULATORY": "PRIMARY_REGULATORY",
    "COMPANY_PRIMARY": "COMPANY_PRIMARY",
    "PRIMARY_COMPANY": "COMPANY_PRIMARY",
    "PRIMARY_COMPANY_EVIDENCE": "COMPANY_PRIMARY",
    "COMPANY_EVIDENCE": "COMPANY_PRIMARY",
    "INSTITUTIONAL_NEWS": "INSTITUTIONAL_NEWS",
    "INSTITUTIONAL_FINANCIAL_NEWS": "INSTITUTIONAL_NEWS",
    "INSTITUTIONAL_MEDIA": "INSTITUTIONAL_NEWS",
    "PROFESSIONAL_RESEARCH": "PROFESSIONAL_RESEARCH",
    "FINANCIAL_PORTAL": "PROFESSIONAL_RESEARCH",
    "MARKET_FINANCIAL_PORTAL": "PROFESSIONAL_RESEARCH",
    "ANALYST_RESEARCH": "PROFESSIONAL_RESEARCH",
    "PROFESSIONAL_CREATOR": "PROFESSIONAL_CREATOR",
    "PROFESSIONAL_VIDEO_PODCAST": "PROFESSIONAL_CREATOR",
    "INDEPENDENT_CREATOR": "PROFESSIONAL_CREATOR",
    "YOUTUBE_PODCAST": "PROFESSIONAL_CREATOR",
    "MARKET_ANALYTICS": "MARKET_ANALYTICS",
    "TECHNICAL_MARKET_ANALYTICS": "MARKET_ANALYTICS",
    "SOCIAL_COMMUNITY": "SOCIAL_COMMUNITY",
    "COMMUNITY_SOCIAL": "SOCIAL_COMMUNITY",
    "SOCIAL_SENTIMENT": "SOCIAL_COMMUNITY",
}

SOURCE_ALIASES: dict[str, str] = {
    "SEC EDGAR DAILY INDEX": "PRIMARY_REGULATORY",
    "SEC EDGAR": "PRIMARY_REGULATORY",
    "SEC FILING": "PRIMARY_REGULATORY",
    "SEC FILINGS": "PRIMARY_REGULATORY",
    "EARNINGS REPORT": "COMPANY_PRIMARY",
    "EARNINGS REPORTS": "COMPANY_PRIMARY",
    "INVESTOR RELATIONS": "COMPANY_PRIMARY",
    "COMPANY INVESTOR RELATIONS": "COMPANY_PRIMARY",
    "REUTERS": "INSTITUTIONAL_NEWS",
    "BLOOMBERG": "INSTITUTIONAL_NEWS",
    "MARKETWATCH": "INSTITUTIONAL_NEWS",
    "CNBC": "INSTITUTIONAL_NEWS",
    "CBS NEWS": "INSTITUTIONAL_NEWS",
    "THE GLOBE AND MAIL": "INSTITUTIONAL_NEWS",
    "YAHOO FINANCE": "PROFESSIONAL_RESEARCH",
    "NASDAQ": "PROFESSIONAL_RESEARCH",
    "NASDAQ.COM": "PROFESSIONAL_RESEARCH",
    "STOCK TITAN": "PROFESSIONAL_RESEARCH",
    "MEDTECH DIVE": "PROFESSIONAL_RESEARCH",
    "MARKETBEAT": "PROFESSIONAL_RESEARCH",
    "WALLSTREETZEN": "PROFESSIONAL_RESEARCH",
    "BOW TIE NATION": "PROFESSIONAL_CREATOR",
    "EARN YOUR LEISURE": "PROFESSIONAL_CREATOR",
    "BWB - BUSINESS WITH BRIAN": "PROFESSIONAL_CREATOR",
    "BUSINESS WITH BRIAN": "PROFESSIONAL_CREATOR",
    "LET'S TALK MONEY": "PROFESSIONAL_CREATOR",
    "LET'S TALK MONEY WITH JOSEPH HOGUE": "PROFESSIONAL_CREATOR",
    "LET'S TALK MONEY! WITH JOSEPH HOGUE, CFA": "PROFESSIONAL_CREATOR",
    "TICKER SYMBOL YOU": "PROFESSIONAL_CREATOR",
    "TICKER SYMBOL: YOU": "PROFESSIONAL_CREATOR",
    "WALL STREET TRAPPER": "PROFESSIONAL_CREATOR",
    "TRADINGVIEW": "MARKET_ANALYTICS",
    "REDDIT": "SOCIAL_COMMUNITY",
    "STOCKTWITS": "SOCIAL_COMMUNITY",
}


def _token(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def normalize_enterprise_source(
    source: object,
    source_class: object = None,
) -> NormalizedEnterpriseSource:
    """Normalize one AI CIO evidence source without granting implicit trust.

    A supplied source_class has priority and must resolve to an approved class.
    When no source_class is supplied, only explicitly known source aliases are
    accepted. Unknown display names are retained in the audit result but rejected
    from trusted Swing evidence.
    """
    original = str(source or "").strip()
    if not original:
        return NormalizedEnterpriseSource(
            original_source="",
            source_class=None,
            accepted=False,
            normalization_method="REJECTED_MALFORMED",
            warning="MALFORMED_ENTERPRISE_SOURCE:MISSING_SOURCE",
        )

    supplied_class = _token(source_class)
    if supplied_class:
        normalized_class = SOURCE_CLASS_ALIASES.get(supplied_class)
        if normalized_class is None:
            return NormalizedEnterpriseSource(
                original_source=original,
                source_class=None,
                accepted=False,
                normalization_method="REJECTED_SOURCE_CLASS",
                warning=f"UNRECOGNIZED_ENTERPRISE_SOURCE_CLASS:{original}:{supplied_class}",
            )
        return NormalizedEnterpriseSource(
            original_source=original,
            source_class=normalized_class,
            accepted=True,
            normalization_method="AI_CIO_SOURCE_CLASS",
        )

    alias_class = SOURCE_ALIASES.get(_token(original))
    if alias_class is None:
        return NormalizedEnterpriseSource(
            original_source=original,
            source_class=None,
            accepted=False,
            normalization_method="REJECTED_UNKNOWN_ALIAS",
            warning=f"UNRECOGNIZED_ENTERPRISE_SOURCE:{original}",
        )
    return NormalizedEnterpriseSource(
        original_source=original,
        source_class=alias_class,
        accepted=True,
        normalization_method="SWING_ALIAS_MAP",
    )


def source_class_profile(source_class: str | None) -> SourceClassProfile | None:
    if not source_class:
        return None
    return SOURCE_CLASS_PROFILES.get(_token(source_class))

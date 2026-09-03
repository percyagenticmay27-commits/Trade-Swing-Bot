"""Discovery Engine variant that enriches themes from trusted current evidence.

This is a narrow integration layer around the existing DiscoveryEngine. It does
not change source weights, lifecycle rules, Theme Momentum math, financial
health, allocation, strategy assignments, positions, or trade behavior.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Mapping, Sequence

from .discovery_engine import (
    APPROVED_THEMES,
    CandidateState,
    DiscoveryEngine,
    FinancialHealth,
    SourceMention,
    WatchlistRow,
    _mention_weight,
    _normalize_theme,
    _recent_mentions,
)
from .theme_enrichment import enrich_candidate_themes


class ThemeEnrichedDiscoveryEngine(DiscoveryEngine):
    """DiscoveryEngine with evidence-derived theme enrichment before scoring."""

    def _evaluate_candidate(
        self,
        candidate: CandidateState,
        mentions: Sequence[SourceMention],
        financial_health: Mapping[str, FinancialHealth],
        as_of: date,
    ) -> WatchlistRow:
        symbol = candidate.underlying_symbol.upper()
        recent = _recent_mentions(symbol, mentions, as_of)
        enriched_themes = enrich_candidate_themes(
            candidate.themes,
            recent,
            approved_themes=APPROVED_THEMES,
            normalize_theme=_normalize_theme,
            mention_weight=_mention_weight,
            mention_themes=lambda mention: mention.themes,
        )
        return super()._evaluate_candidate(
            replace(candidate, themes=enriched_themes),
            mentions,
            financial_health,
            as_of,
        )

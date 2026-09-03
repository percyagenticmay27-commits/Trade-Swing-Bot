"""Evidence-derived theme enrichment for Discovery candidates.

Themes are inferred only from approved theme tags already present on trusted,
positive-weight Discovery mentions for the same underlying symbol. No per-symbol
company/theme mapping is hardcoded here.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

MentionT = TypeVar("MentionT")


def enrich_candidate_themes(
    candidate_themes: Sequence[str],
    mentions: Sequence[MentionT],
    *,
    approved_themes: set[str],
    normalize_theme: Callable[[str], str],
    mention_weight: Callable[[MentionT, Sequence[MentionT]], int],
    mention_themes: Callable[[MentionT], Sequence[str]],
) -> tuple[str, ...]:
    """Merge configured themes with approved themes supported by trusted evidence.

    Existing configured themes are preserved when approved. Evidence can enrich
    DISCOVERY, MONITOR, WATCHLIST, or any other candidate state because lifecycle
    is intentionally not an input to this function.
    """
    enriched: dict[str, str] = {}

    for theme in candidate_themes:
        normalized = normalize_theme(theme)
        if normalized in approved_themes:
            enriched.setdefault(normalized, theme.strip())

    for mention in mentions:
        if mention_weight(mention, mentions) <= 0:
            continue
        for theme in mention_themes(mention):
            normalized = normalize_theme(theme)
            if normalized in approved_themes:
                # Use canonical title-like spelling from the approved vocabulary
                # rather than binding a theme to a company symbol.
                canonical = next(value for value in approved_themes if value == normalized)
                enriched.setdefault(normalized, canonical.title())

    return tuple(enriched[key] for key in sorted(enriched))

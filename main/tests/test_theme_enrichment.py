from dataclasses import dataclass

from swing_trade_bot.theme_enrichment import enrich_candidate_themes


@dataclass(frozen=True)
class Mention:
    themes: tuple[str, ...]
    weight: int = 1


def enrich(existing, mentions):
    approved={"AI INFRASTRUCTURE","DATA CENTERS","SEMICONDUCTORS"}
    return enrich_candidate_themes(
        existing,
        mentions,
        approved_themes=approved,
        normalize_theme=lambda value:value.strip().upper(),
        mention_weight=lambda item, _:item.weight,
        mention_themes=lambda item:item.themes,
    )


def test_empty_existing_themes_are_enriched_from_trusted_evidence():
    assert enrich((), [Mention(("Semiconductors",))]) == ("Semiconductors",)


def test_existing_theme_and_evidence_theme_are_merged():
    assert enrich(("AI Infrastructure",), [Mention(("Data Centers",))]) == ("AI Infrastructure","Data Centers")


def test_untrusted_evidence_cannot_assign_theme():
    assert enrich((), [Mention(("Semiconductors",), weight=0)]) == ()


def test_unapproved_theme_cannot_be_assigned():
    assert enrich((), [Mention(("Consumer Retail",))]) == ()


def test_enrichment_has_no_lifecycle_dependency():
    # The helper intentionally receives no DISCOVERY/MONITOR/WATCHLIST status,
    # so the same evidence enriches an already-WATCHLIST candidate.
    assert enrich((), [Mention(("AI Infrastructure",))]) == ("Ai Infrastructure",)

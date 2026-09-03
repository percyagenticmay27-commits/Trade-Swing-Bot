from datetime import date, timedelta

from swing_trade_bot.discovery_engine import CandidateState, FinancialHealth, SourceMention
from swing_trade_bot.theme_enriched_discovery import ThemeEnrichedDiscoveryEngine

AS_OF = date(2026, 9, 3)


def _health(value=80.0):
    return FinancialHealth(value, value, value, value, value, value, value)


def test_existing_watchlist_candidate_gets_theme_from_trusted_mentions():
    candidate = CandidateState(
        underlying_symbol="NVDA",
        leveraged_symbol="NVDX",
        status="WATCHLIST",
        themes=(),
    )
    mentions = [
        SourceMention("NVDA", "Bloomberg", AS_OF - timedelta(days=3), ("Semiconductors",)),
        SourceMention("NVDA", "Reuters", AS_OF - timedelta(days=2), ("Semiconductors",)),
    ]
    row = ThemeEnrichedDiscoveryEngine().evaluate(
        [candidate], mentions, {"NVDA": _health()}, as_of=AS_OF
    )[0]
    assert row.watchlist_status == "WATCHLIST"
    assert row.themes == "Semiconductors"
    assert row.theme_momentum_score > 0


def test_enrichment_is_lifecycle_independent():
    mentions = [
        SourceMention("NVDA", "Bloomberg", AS_OF - timedelta(days=3), ("Semiconductors",)),
        SourceMention("NVDA", "Reuters", AS_OF - timedelta(days=2), ("Semiconductors",)),
    ]
    for status in ("DISCOVERY", "MONITOR", "WATCHLIST"):
        row = ThemeEnrichedDiscoveryEngine().evaluate(
            [CandidateState("NVDA", "NVDX", status=status)],
            mentions,
            {"NVDA": _health()},
            as_of=AS_OF,
        )[0]
        assert row.themes == "Semiconductors"
        assert row.theme_momentum_score > 0


def test_untrusted_enterprise_theme_does_not_enrich_watchlist():
    candidate = CandidateState("PLTR", "PLTU", status="WATCHLIST")
    mentions = [
        SourceMention(
            "PLTR",
            "Reddit",
            AS_OF - timedelta(days=1),
            ("AI Infrastructure",),
            source_class="SOCIAL_COMMUNITY",
        )
    ]
    row = ThemeEnrichedDiscoveryEngine().evaluate(
        [candidate], mentions, {"PLTR": _health()}, as_of=AS_OF
    )[0]
    assert row.themes == ""
    assert row.theme_momentum_score == 0.0


def test_leveraged_vehicle_theme_evidence_cannot_enrich_underlying():
    candidate = CandidateState("AMZN", "AMZU", status="WATCHLIST")
    mentions = [
        SourceMention("AMZU", "Bloomberg", AS_OF - timedelta(days=1), ("Cloud Computing",))
    ]
    row = ThemeEnrichedDiscoveryEngine().evaluate(
        [candidate], mentions, {"AMZN": _health()}, as_of=AS_OF
    )[0]
    assert row.underlying_symbol == "AMZN"
    assert row.themes == ""
    assert row.theme_momentum_score == 0.0

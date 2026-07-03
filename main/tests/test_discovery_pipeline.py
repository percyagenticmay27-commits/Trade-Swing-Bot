import csv
import unittest
import uuid
from datetime import date
from pathlib import Path

from swing_trade_bot.discovery_scheduler import DiscoveryScheduler, merge_mention_files
from swing_trade_bot.mention_extractor import read_discovery_mentions_csv, write_discovery_mentions_csv
from swing_trade_bot.news_feed_collector import NewsFeedCollector
from swing_trade_bot.youtube_feed_collector import YouTubeFeedCollector


AS_OF = date(2026, 6, 24)


class DiscoveryPipelineTests(unittest.TestCase):
    def test_youtube_feed_collection_writes_mentions(self) -> None:
        with workspace_temp_dir() as directory:
            feed = write_youtube_feed(directory)
            output = directory / "youtube_mentions.csv"

            YouTubeFeedCollector().write_mentions(feed, output)
            mentions = read_discovery_mentions_csv(output)

        self.assertEqual({mention.underlying_symbol for mention in mentions}, {"NBIS", "NEBX"})
        self.assertTrue(all(mention.source_type == "YOUTUBE" for mention in mentions))

    def test_news_feed_collection_writes_mentions(self) -> None:
        with workspace_temp_dir() as directory:
            feed = write_news_feed(directory)
            output = directory / "news_mentions.csv"

            NewsFeedCollector().write_mentions(feed, output)
            mentions = read_discovery_mentions_csv(output)

        self.assertIn("NBIS", {mention.underlying_symbol for mention in mentions})
        self.assertTrue(all(mention.source_type == "INSTITUTIONAL" for mention in mentions))

    def test_duplicate_removal_merges_by_symbol_source_and_date(self) -> None:
        with workspace_temp_dir() as directory:
            feed = write_news_feed(directory)
            first = directory / "first.csv"
            second = directory / "second.csv"
            merged = directory / "discovery_mentions.csv"
            collector = NewsFeedCollector()
            collector.write_mentions(feed, first)
            collector.write_mentions(feed, second)

            merge_mention_files(merged, [first, second])
            mentions = read_discovery_mentions_csv(merged)

        nbis_reuters = [
            mention
            for mention in mentions
            if mention.underlying_symbol == "NBIS" and mention.source == "Reuters"
        ]
        self.assertEqual(len(nbis_reuters), 1)

    def test_scheduler_execution_generates_all_outputs(self) -> None:
        with workspace_temp_dir() as directory:
            result = run_scheduler(directory)

            self.assertTrue(result.youtube_mentions_path.exists())
            self.assertTrue(result.news_mentions_path.exists())
            self.assertTrue(result.discovery_mentions_path.exists())
            self.assertTrue(result.watchlist_csv_path.exists())
            self.assertTrue(result.watchlist_json_path.exists())
            self.assertTrue(result.discovery_summary_path.exists())

    def test_watchlist_generation_contains_candidate_status(self) -> None:
        with workspace_temp_dir() as directory:
            result = run_scheduler(directory)
            with result.watchlist_csv_path.open(newline="", encoding="utf-8") as input_file:
                rows = list(csv.DictReader(input_file))

        nbis = next(row for row in rows if row["underlying_symbol"] == "NBIS")
        self.assertEqual(nbis["watchlist_status"], "LOW")
        self.assertEqual(nbis["source_confluence_level"], "HIGH_PRIORITY_WATCHLIST")

    def test_summary_generation_contains_monitoring_fields(self) -> None:
        with workspace_temp_dir() as directory:
            result = run_scheduler(directory)
            with result.discovery_summary_path.open(newline="", encoding="utf-8") as input_file:
                rows = list(csv.DictReader(input_file))

        nbis = next(row for row in rows if row["symbol"] == "NBIS")
        self.assertEqual(nbis["mention_count_30d"], "3")
        self.assertEqual(nbis["source_count"], "3")
        self.assertEqual(nbis["watchlist_status"], "LOW")
        self.assertGreater(float(nbis["composite_score"]), 0.0)

    def test_scheduler_rejects_live_mode(self) -> None:
        with self.assertRaises(ValueError):
            DiscoveryScheduler(paper_trade_mode=False)


def run_scheduler(directory: Path):
    return DiscoveryScheduler().run(
        youtube_feed=write_youtube_feed(directory),
        news_feed=write_news_feed(directory),
        candidates_path=write_candidates(directory),
        financial_health_path=write_financial_health(directory),
        output_dir=directory / "results",
        mode="daily",
        as_of=AS_OF,
    )


def write_youtube_feed(directory: Path) -> Path:
    path = directory / "youtube_feed.csv"
    path.write_text(
        "\n".join(
            [
                "channel_name,title,description,publish_date,video_url,transcript",
                "Bow Tie Nation,NBIS and NEBX AI infrastructure watchlist,AI data center demand,2026-06-24,https://example.com/yt/nbis,",
                "Unknown Channel,IREN bitcoin mining idea,Unapproved source,2026-06-24,https://example.com/yt/iren,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_news_feed(directory: Path) -> Path:
    path = directory / "news_feed.csv"
    path.write_text(
        "\n".join(
            [
                "source,title,publish_date,url,article_text",
                "Reuters,NBIS expands AI infrastructure and data center capacity,2026-06-24,https://example.com/news/nbis,Analyst upgrade highlights AI data center growth.",
                "Bloomberg,NBIS AI infrastructure capex rises,2026-06-24,https://example.com/news/nbis-bloomberg,Data center demand expands.",
                "Random Blog,NBIS should be ignored,2026-06-24,https://example.com/news/random,Unapproved source.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_candidates(directory: Path) -> Path:
    path = directory / "candidates.csv"
    path.write_text(
        "\n".join(
            [
                "underlying_symbol,leveraged_symbol,status,paper_return,win_rate,profit_factor,number_of_trades,trading_days,days_in_status,earnings_stability_score,leveraged_vehicle_exists,themes",
                "NBIS,NEBX,WATCHLIST,12.5,45,1.8,10,90,90,72,true,AI Infrastructure;Data Centers",
                "IREN,IREL,DISCOVERY,0,0,0,0,0,0,65,true,Bitcoin Mining;Data Centers",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_financial_health(directory: Path) -> Path:
    path = directory / "financial_health.csv"
    path.write_text(
        "\n".join(
            [
                "underlying_symbol,revenue_growth,eps_growth,operating_cash_flow,gross_margin_trend,debt_health,analyst_revisions,sector_strength",
                "NBIS,82,78,74,80,72,76,79",
                "IREN,75,70,68,72,65,73,78",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def workspace_temp_dir():
    class WorkspaceTempDir:
        def __init__(self) -> None:
            self.path = Path.cwd() / f"discovery_pipeline_test_{uuid.uuid4().hex}"

        def __enter__(self) -> Path:
            self.path.mkdir()
            return self.path

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            for child in sorted(self.path.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                else:
                    child.rmdir()
            self.path.rmdir()

    return WorkspaceTempDir()


if __name__ == "__main__":
    unittest.main()

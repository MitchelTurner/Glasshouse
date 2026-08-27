import unittest
from unittest.mock import patch

from src.research.web_search import enrich_ideas_with_research


class ResearchEnrichmentTests(unittest.TestCase):
    def test_skips_already_used_articles(self):
        hits = [
            {"title": "Old clip", "url": "https://www.news.com/old", "snippet": "seen"},
            {"title": "Fresh clip", "url": "https://news.com/fresh", "snippet": "new"},
        ]
        with patch("src.research.web_search.research_topic", return_value=hits):
            ideas = enrich_ideas_with_research(
                [{"title": "Housing", "research_queries": ["housing vote"]}],
                max_queries=1,
                exclude_urls={"https://news.com/old"},
            )
        results = ideas[0]["background_research"][0]["results"]
        self.assertEqual([item["url"] for item in results], ["https://news.com/fresh"])


if __name__ == "__main__":
    unittest.main()

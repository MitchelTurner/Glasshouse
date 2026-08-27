import unittest

from src.db.covered_stories import story_content_hash
from src.novelty import (
    extract_research_urls,
    filter_research_hits,
    format_covered_prompt_lines,
    is_near_duplicate,
    normalize_url,
    split_novel_ideas,
)


class NoveltyMatchingTests(unittest.TestCase):
    def test_rephrased_title_is_duplicate(self):
        covered = [
            {
                "title": "School Board Budget Fight",
                "hook": "Cuts could hit classrooms",
                "meeting_source": "School Board - Jan 2025",
            }
        ]
        idea = {
            "title": "The School Board's Budget Battle",
            "hook": "Classroom cuts are on the table",
            "meeting_source": "School Board - January 2025",
        }
        self.assertTrue(is_near_duplicate(idea, covered))

    def test_unrelated_story_is_kept(self):
        covered = [{"title": "School Board Budget Fight", "hook": "Cuts could hit classrooms"}]
        idea = {
            "title": "County Approves New Riverfront Housing",
            "hook": "200 units planned near downtown",
            "angle": "zoning vote and neighborhood opposition",
        }
        self.assertFalse(is_near_duplicate(idea, covered))

    def test_same_batch_variants_are_collapsed(self):
        ideas = [
            {"title": "Police Oversight Board Deadlocks on Discipline"},
            {"title": "Police Oversight Board Deadlock on Officer Discipline"},
            {"title": "Library Hours Expand on Weekends"},
        ]
        novel, skipped = split_novel_ideas(ideas)
        self.assertEqual([idea["title"] for idea in novel], [
            "Police Oversight Board Deadlocks on Discipline",
            "Library Hours Expand on Weekends",
        ])
        self.assertEqual(len(skipped), 1)

    def test_blank_titles_are_skipped(self):
        novel, skipped = split_novel_ideas([{"title": "  "}, {"title": "Water Rate Hike"}])
        self.assertEqual(len(novel), 1)
        self.assertEqual(len(skipped), 1)

    def test_normalized_hash_treats_word_order_as_same_story(self):
        first = story_content_hash({
            "title": "The Budget Fight at City Council",
            "meeting_source": "City Council Meeting",
        })
        second = story_content_hash({
            "title": "City Council budget fight!",
            "meeting_source": "City Council Meeting",
        })
        self.assertEqual(first, second)


class ResearchDedupTests(unittest.TestCase):
    def test_normalize_url_strips_www_and_slash(self):
        self.assertEqual(
            normalize_url("https://WWW.Example.com/story/?utm=1"),
            "https://example.com/story",
        )

    def test_filter_research_hits_skips_known_urls(self):
        hits = [
            {"title": "Old", "url": "https://www.news.com/a/"},
            {"title": "New", "url": "https://news.com/b"},
        ]
        fresh = filter_research_hits(hits, {"https://news.com/a"}, limit=2)
        self.assertEqual([hit["title"] for hit in fresh], ["New"])

    def test_extract_research_urls_from_story_or_idea(self):
        stories = [
            {
                "background_research": [
                    {"results": [{"url": "https://www.news.com/a/"}]}
                ]
            },
            {
                "idea": {
                    "background_research": [
                        {"results": [{"url": "https://news.com/b"}]}
                    ]
                }
            },
        ]
        self.assertEqual(
            extract_research_urls(stories),
            {"https://news.com/a", "https://news.com/b"},
        )

    def test_prompt_lines_include_title_and_meeting(self):
        lines = format_covered_prompt_lines(
            [
                {
                    "title": "Budget Fight",
                    "hook": "Cuts incoming",
                    "meeting_source": "School Board",
                    "covered_at": "2026-08-20T12:00:00",
                }
            ]
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("Budget Fight", lines[0])
        self.assertIn("School Board", lines[0])
        self.assertIn("2026-08-20", lines[0])


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime
from unittest.mock import patch

from src.config import Settings
from src.db.transcripts import MeetingTranscript, select_transcripts_for_scope
from src.llm.claude import get_system_prompt
from src.notifications.telegram import format_ideas_message
from src.services.pipeline import (
    _already_covered_prompt_lines,
    _attach_meeting_dates,
    run_pipeline_for_transcripts,
)


def _meeting(transcript_id: int, title: str) -> MeetingTranscript:
    return MeetingTranscript(
        transcript_id=transcript_id,
        video_id=f"vid-{transcript_id}",
        title=title,
        meeting_type="city_council",
        published_at=datetime(2026, 8, 20, 12, 0, 0),
        full_text="transcript",
        word_count=10,
    )


class ScopeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(analyze_scope="new_or_latest", max_latest_meetings=2)
        self.recent = [
            _meeting(3, "Newest"),
            _meeting(2, "Middle"),
            _meeting(1, "Oldest"),
        ]

    def test_recent_returns_all(self):
        with patch(
            "src.db.transcripts.fetch_recent_meeting_transcripts",
            return_value=self.recent,
        ):
            selected = select_transcripts_for_scope(self.settings, "recent")
        self.assertEqual([item.title for item in selected], ["Newest", "Middle", "Oldest"])

    def test_latest_caps_to_max_latest_meetings(self):
        with patch(
            "src.db.transcripts.fetch_recent_meeting_transcripts",
            return_value=self.recent,
        ):
            selected = select_transcripts_for_scope(self.settings, "latest")
        self.assertEqual([item.title for item in selected], ["Newest", "Middle"])

    def test_new_or_latest_prefers_unprocessed(self):
        unprocessed = [_meeting(9, "Brand new")]
        with (
            patch(
                "src.db.transcripts.fetch_unprocessed_meeting_transcripts",
                return_value=unprocessed,
            ),
            patch(
                "src.db.transcripts.fetch_recent_meeting_transcripts",
                return_value=self.recent,
            ),
        ):
            selected = select_transcripts_for_scope(self.settings, "new_or_latest")
        self.assertEqual([item.title for item in selected], ["Brand new"])

    def test_new_or_latest_falls_back_to_latest(self):
        with (
            patch(
                "src.db.transcripts.fetch_unprocessed_meeting_transcripts",
                return_value=[],
            ),
            patch(
                "src.db.transcripts.fetch_recent_meeting_transcripts",
                return_value=self.recent,
            ),
        ):
            selected = select_transcripts_for_scope(self.settings, "new_or_latest")
        self.assertEqual([item.title for item in selected], ["Newest", "Middle"])


class PromptAndMessageTests(unittest.TestCase):
    def test_system_prompt_asks_for_fresh_stories(self):
        prompt = get_system_prompt(
            already_covered=["[2026-08-20] Budget Fight — School Board"],
        )
        self.assertIn("Already covered stories", prompt)
        self.assertIn("Budget Fight", prompt)
        self.assertIn("newest meetings", prompt.lower())

    def test_empty_ideas_message_explains_repeats(self):
        text = format_ideas_message(
            "Nothing new",
            [],
            skipped_duplicate_count=3,
            meeting_titles=["City Council - Aug 20"],
        )
        self.assertIn("No new video ideas", text)
        self.assertIn("City Council - Aug 20", text)
        self.assertIn("3 repeat idea(s) hidden", text)

    def test_ideas_message_notes_hidden_repeats(self):
        text = format_ideas_message(
            "Fresh set",
            [{"title": "Riverfront Housing Vote", "meeting_source": "Council", "meeting_date": "2026-08-20"}],
            skipped_duplicate_count=2,
        )
        self.assertIn("Riverfront Housing Vote", text)
        self.assertIn("2026-08-20", text)
        self.assertIn("2 already-covered idea(s) hidden", text)

    def test_attach_meeting_dates_matches_source(self):
        ideas = _attach_meeting_dates(
            [{"title": "Housing", "meeting_source": "Newest Meeting"}],
            [_meeting(1, "Newest Meeting")],
        )
        self.assertEqual(ideas[0]["meeting_date"], "2026-08-20")

    def test_already_covered_prompt_includes_article_urls(self):
        lines = _already_covered_prompt_lines(
            [
                {
                    "title": "Budget Fight",
                    "hook": "Cuts incoming",
                    "meeting_source": "School Board",
                    "covered_at": "2026-08-20",
                    "background_research": [
                        {"results": [{"url": "https://www.news.com/budget"}]}
                    ],
                }
            ]
        )
        self.assertTrue(any("Budget Fight" in line for line in lines))
        self.assertIn("Already used research links (do not cite again):", lines)
        self.assertIn("https://news.com/budget", lines)


class PipelineFilterTests(unittest.TestCase):
    def test_pipeline_keeps_only_new_ideas(self):
        settings = Settings(telegram_bot_token="", telegram_chat_id="")
        covered = [
            {
                "title": "School Board Budget Fight",
                "hook": "Cuts could hit classrooms",
                "meeting_source": "School Board",
            }
        ]
        analysis = {
            "summary": "Two ideas",
            "ideas": [
                {
                    "title": "The School Board Budget Battle",
                    "meeting_source": "School Board",
                    "hook": "Classroom cuts incoming",
                },
                {
                    "title": "Library Hours Expand on Weekends",
                    "meeting_source": "School Board",
                    "hook": "Saturday hours return",
                },
            ],
        }

        with (
            patch("src.services.pipeline.ensure_covered_stories_backfilled"),
            patch("src.services.pipeline.get_covered_story_context", return_value=covered),
            patch("src.services.pipeline.analyze_transcripts", return_value=analysis) as analyze,
            patch(
                "src.services.pipeline.enrich_ideas_with_research",
                side_effect=lambda ideas, *_args, **_kwargs: ideas,
            ),
            patch("src.services.pipeline.save_analysis_run", return_value=11),
            patch("src.services.pipeline.save_covered_stories") as save_stories,
            patch("src.services.pipeline.mark_transcripts_processed") as mark,
        ):
            result = run_pipeline_for_transcripts(
                [_meeting(1, "School Board")],
                settings,
                dry_run=True,
                send_telegram=False,
                guidance={},
            )

        self.assertEqual(result.idea_count, 1)
        self.assertEqual(result.skipped_duplicate_count, 1)
        self.assertEqual(result.analysis["ideas"][0]["title"], "Library Hours Expand on Weekends")
        save_stories.assert_called_once()
        self.assertEqual(save_stories.call_args[0][0][0]["title"], "Library Hours Expand on Weekends")
        mark.assert_called_once()
        analyze.assert_called_once()


if __name__ == "__main__":
    unittest.main()

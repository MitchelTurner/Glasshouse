from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg2
import psycopg2.extras

from src.config import Settings


@dataclass
class MeetingTranscript:
    transcript_id: int
    video_id: str
    title: str
    meeting_type: str | None
    published_at: datetime | None
    full_text: str
    word_count: int


def get_connection(settings: Settings):
    return psycopg2.connect(settings.database_url)


def fetch_recent_meeting_transcripts(settings: Settings) -> list[MeetingTranscript]:
    query = """
        SELECT
            t.id AS transcript_id,
            v.video_id,
            v.title,
            v.meeting_type,
            v.published_at,
            t.full_text,
            COALESCE(t.word_count, LENGTH(t.full_text) / 5) AS word_count
        FROM transcripts t
        JOIN videos v ON v.id = t.video_id
        WHERE v.is_meeting = TRUE
          AND (
              v.published_at IS NULL
              OR v.published_at >= NOW() - (%s || ' days')::INTERVAL
          )
        ORDER BY v.published_at DESC NULLS LAST, t.fetched_at DESC
        LIMIT %s
    """
    with get_connection(settings) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (settings.lookback_days, settings.max_transcripts))
            rows = cur.fetchall()

    return [
        MeetingTranscript(
            transcript_id=row["transcript_id"],
            video_id=row["video_id"],
            title=row["title"],
            meeting_type=row["meeting_type"],
            published_at=row["published_at"],
            full_text=row["full_text"],
            word_count=int(row["word_count"] or 0),
        )
        for row in rows
    ]


def save_analysis_run(
    settings: Settings,
    transcript_ids: list[int],
    ideas_json: dict,
    telegram_sent: bool,
) -> int:
    query = """
        INSERT INTO analysis_runs (transcripts, ideas_json, telegram_sent)
        VALUES (%s, %s, %s)
        RETURNING id
    """
    with get_connection(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (transcript_ids, psycopg2.extras.Json(ideas_json), telegram_sent),
            )
            run_id = cur.fetchone()[0]
        conn.commit()
    return run_id

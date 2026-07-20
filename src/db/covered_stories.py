"""Persist covered news/video ideas in PostgreSQL.

After each pipeline run, individual story ideas (plus research) are stored
in `covered_stories` so Glasshouse can avoid re-covering the same topics
and other software sharing the database can query them.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import psycopg2.extras

from src.config import Settings, get_settings
from src.db.connection import get_connection

ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS covered_stories (
    id                  SERIAL PRIMARY KEY,
    analysis_run_id     INTEGER,
    transcript_ids      INTEGER[] NOT NULL DEFAULT '{}',
    title               TEXT NOT NULL,
    meeting_source      TEXT,
    hook                TEXT,
    angle               TEXT,
    key_points          JSONB NOT NULL DEFAULT '[]',
    research_queries    JSONB NOT NULL DEFAULT '[]',
    background_research JSONB NOT NULL DEFAULT '[]',
    urgency             TEXT,
    estimated_length    TEXT,
    content_hash        TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL DEFAULT 'covered',
    idea_json           JSONB NOT NULL,
    covered_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

ENSURE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_covered_stories_covered_at ON covered_stories(covered_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_covered_stories_status ON covered_stories(status)",
    "CREATE INDEX IF NOT EXISTS idx_covered_stories_run ON covered_stories(analysis_run_id)",
]


def _ensure_table(settings: Settings) -> None:
    with get_connection(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(ENSURE_TABLE_SQL)
            for statement in ENSURE_INDEXES_SQL:
                cur.execute(statement)
        conn.commit()


def story_content_hash(idea: dict) -> str:
    title = " ".join(str(idea.get("title") or "").lower().split())
    meeting = " ".join(str(idea.get("meeting_source") or "").lower().split())
    payload = f"{title}|{meeting}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    return value


def save_covered_stories(
    ideas: list[dict],
    transcript_ids: list[int],
    *,
    analysis_run_id: int | None = None,
    settings: Settings | None = None,
) -> list[int]:
    """Insert or update covered story rows. Returns saved row IDs."""
    if not ideas:
        return []

    settings = settings or get_settings()
    _ensure_table(settings)
    saved_ids: list[int] = []

    with get_connection(settings) as conn:
        with conn.cursor() as cur:
            for idea in ideas:
                title = str(idea.get("title") or "").strip()
                if not title:
                    continue

                content_hash = story_content_hash(idea)
                cur.execute(
                    """
                    INSERT INTO covered_stories (
                        analysis_run_id,
                        transcript_ids,
                        title,
                        meeting_source,
                        hook,
                        angle,
                        key_points,
                        research_queries,
                        background_research,
                        urgency,
                        estimated_length,
                        content_hash,
                        status,
                        idea_json,
                        covered_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'covered', %s, NOW()
                    )
                    ON CONFLICT (content_hash) DO UPDATE SET
                        analysis_run_id = COALESCE(EXCLUDED.analysis_run_id, covered_stories.analysis_run_id),
                        transcript_ids = EXCLUDED.transcript_ids,
                        title = EXCLUDED.title,
                        meeting_source = EXCLUDED.meeting_source,
                        hook = EXCLUDED.hook,
                        angle = EXCLUDED.angle,
                        key_points = EXCLUDED.key_points,
                        research_queries = EXCLUDED.research_queries,
                        background_research = EXCLUDED.background_research,
                        urgency = EXCLUDED.urgency,
                        estimated_length = EXCLUDED.estimated_length,
                        idea_json = EXCLUDED.idea_json,
                        covered_at = NOW()
                    RETURNING id
                    """,
                    (
                        analysis_run_id,
                        transcript_ids,
                        title,
                        idea.get("meeting_source"),
                        idea.get("hook"),
                        idea.get("angle"),
                        psycopg2.extras.Json(_as_json(idea.get("key_points"), [])),
                        psycopg2.extras.Json(_as_json(idea.get("research_queries"), [])),
                        psycopg2.extras.Json(_as_json(idea.get("background_research"), [])),
                        idea.get("urgency"),
                        idea.get("estimated_length"),
                        content_hash,
                        psycopg2.extras.Json(idea),
                    ),
                )
                row = cur.fetchone()
                if row:
                    saved_ids.append(row[0])
        conn.commit()

    return saved_ids


def list_covered_stories(
    settings: Settings | None = None,
    *,
    limit: int = 50,
    status: str | None = None,
) -> list[dict]:
    settings = settings or get_settings()
    try:
        _ensure_table(settings)
    except Exception:
        return []

    limit = max(1, min(int(limit), 200))
    query = """
        SELECT
            id,
            analysis_run_id,
            transcript_ids,
            title,
            meeting_source,
            hook,
            angle,
            key_points,
            research_queries,
            background_research,
            urgency,
            estimated_length,
            status,
            idea_json,
            covered_at
        FROM covered_stories
    """
    params: list[Any] = []
    if status:
        query += " WHERE status = %s"
        params.append(status)
    query += " ORDER BY covered_at DESC LIMIT %s"
    params.append(limit)

    with get_connection(settings) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

    return [_serialize_story(row) for row in rows]


def get_recent_covered_titles(
    settings: Settings | None = None,
    *,
    limit: int = 40,
) -> list[str]:
    """Titles of recently covered stories for LLM dedup context."""
    stories = list_covered_stories(settings, limit=limit)
    titles: list[str] = []
    for story in stories:
        title = str(story.get("title") or "").strip()
        if title and title not in titles:
            titles.append(title)
    return titles


def load_latest_analysis_from_db(settings: Settings | None = None) -> dict | None:
    """Rebuild the latest analysis payload from Postgres when the local file is missing."""
    settings = settings or get_settings()
    try:
        with get_connection(settings) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ideas_json, run_at
                    FROM analysis_runs
                    ORDER BY run_at DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
        if not row:
            return None
        payload = row["ideas_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            return None
        analysis = dict(payload)
        run_at = row.get("run_at")
        if isinstance(run_at, datetime):
            analysis.setdefault("run_at", run_at.isoformat())
        return analysis
    except Exception:
        return None


def _serialize_story(row: dict) -> dict:
    covered_at = row.get("covered_at")
    idea_json = row.get("idea_json")
    if isinstance(idea_json, str):
        try:
            idea_json = json.loads(idea_json)
        except json.JSONDecodeError:
            idea_json = {"raw": idea_json}

    return {
        "id": row["id"],
        "analysis_run_id": row.get("analysis_run_id"),
        "transcript_ids": list(row.get("transcript_ids") or []),
        "title": row.get("title"),
        "meeting_source": row.get("meeting_source"),
        "hook": row.get("hook"),
        "angle": row.get("angle"),
        "key_points": _json_list(row.get("key_points")),
        "research_queries": _json_list(row.get("research_queries")),
        "background_research": _json_list(row.get("background_research")),
        "urgency": row.get("urgency"),
        "estimated_length": row.get("estimated_length"),
        "status": row.get("status"),
        "idea": idea_json if isinstance(idea_json, dict) else {},
        "covered_at": covered_at.isoformat() if isinstance(covered_at, datetime) else covered_at,
    }


def _json_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return list(value) if value else []

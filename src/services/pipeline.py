"""Main analysis pipeline: transcripts → Claude → research → Telegram.

Orchestrates the full flow from fetching meeting transcripts through
LLM analysis, web research enrichment, Telegram delivery, and recording
the run plus individual covered stories in Postgres.

Entry points:
  run_pipeline()                  — new/latest meetings by default (CLI / dashboard)
  run_pipeline_for_new_meetings() — daily scan: unprocessed only
  run_pipeline_for_latest_meeting() — Telegram /latest command
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.config import Settings, get_settings
from src.db.covered_stories import (
    ensure_covered_stories_backfilled,
    get_covered_story_context,
    load_latest_analysis_from_db,
    save_covered_stories,
)
from src.db.processed import mark_transcripts_processed
from src.db.transcripts import (
    MeetingTranscript,
    fetch_latest_meeting_transcript,
    fetch_unprocessed_meeting_transcripts,
    save_analysis_run,
    select_transcripts_for_scope,
)
from src.llm.claude import analyze_transcripts
from src.notifications.telegram import format_ideas_message, send_telegram_message
from src.novelty import (
    extract_research_urls,
    format_covered_prompt_lines,
    split_novel_ideas,
)
from src.research.web_search import enrich_ideas_with_research
from src.services.prompt_settings import load_guidance

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "output" / "latest_ideas.json"


@dataclass
class PipelineResult:
    transcript_count: int
    idea_count: int
    analysis: dict
    telegram_sent: bool
    telegram_preview: str
    run_id: int | None
    output_path: str
    transcript_ids: list[int]
    skipped_duplicate_count: int = 0
    scope: str = "new_or_latest"
    skipped_ideas: list[dict] = field(default_factory=list)


def _transcripts_to_payload(transcripts: list[MeetingTranscript]) -> list[dict]:
    return [
        {
            "transcript_id": t.transcript_id,
            "title": t.title,
            "meeting_type": t.meeting_type,
            "published_at": t.published_at.isoformat() if t.published_at else None,
            "text": t.full_text,
        }
        for t in transcripts
    ]


def _attach_meeting_dates(ideas: list[dict], transcripts: list[MeetingTranscript]) -> list[dict]:
    dated: list[dict] = []
    for idea in ideas:
        updated = dict(idea)
        source = str(updated.get("meeting_source") or "").strip().lower()
        for transcript in transcripts:
            title = transcript.title.lower()
            if source and (title in source or source in title):
                if transcript.published_at:
                    updated["meeting_date"] = transcript.published_at.date().isoformat()
                break
        else:
            if transcripts and transcripts[0].published_at and len(transcripts) == 1:
                updated["meeting_date"] = transcripts[0].published_at.date().isoformat()
        dated.append(updated)
    return dated


def _already_covered_prompt_lines(covered: list[dict]) -> list[str]:
    lines = format_covered_prompt_lines(covered)
    article_urls = sorted(extract_research_urls(covered))
    if article_urls:
        lines.append("Already used research links (do not cite again):")
        lines.extend(article_urls[:40])
    return lines


def _analyze_novel_ideas(
    settings: Settings,
    payload: list[dict],
    guidance: dict | None,
    covered: list[dict],
) -> tuple[dict, list[dict], list[dict]]:
    covered_lines = _already_covered_prompt_lines(covered)
    analysis = analyze_transcripts(
        settings,
        payload,
        guidance=guidance,
        already_covered=covered_lines or None,
    )
    ideas = [idea for idea in analysis.get("ideas", []) if isinstance(idea, dict)]
    novel, skipped = split_novel_ideas(ideas, covered)

    if not novel and ideas:
        rejected = [str(idea.get("title") or "untitled").strip() for idea in ideas]
        retry_lines = covered_lines + [
            "REJECTED THIS RUN because they repeat already-covered stories. "
            "Propose different items from the newest meetings only:",
            *rejected,
        ]
        analysis = analyze_transcripts(
            settings,
            payload,
            guidance=guidance,
            already_covered=retry_lines,
        )
        ideas = [idea for idea in analysis.get("ideas", []) if isinstance(idea, dict)]
        novel, skipped_retry = split_novel_ideas(ideas, covered + skipped)
        skipped = skipped + skipped_retry

    return analysis, novel, skipped


def run_pipeline_for_transcripts(
    transcripts: list[MeetingTranscript],
    settings: Settings | None = None,
    *,
    dry_run: bool = False,
    send_telegram: bool | None = None,
    guidance: dict | None = None,
    mark_processed: bool = True,
    scope: str = "new_or_latest",
) -> PipelineResult:
    if not transcripts:
        raise ValueError("No transcripts provided for analysis.")

    settings = settings or get_settings()
    guidance = guidance or load_guidance()
    payload = _transcripts_to_payload(transcripts)
    ensure_covered_stories_backfilled(settings)
    covered = get_covered_story_context(settings)

    analysis, ideas, skipped = _analyze_novel_ideas(
        settings,
        payload,
        guidance,
        covered,
    )
    ideas = _attach_meeting_dates(ideas, transcripts)
    used_article_urls = extract_research_urls(covered)

    if ideas:
        ideas = enrich_ideas_with_research(
            ideas,
            settings.max_research_queries,
            exclude_urls=used_article_urls,
        )

    if ideas:
        summary = analysis.get("summary", "Video topic ideas from recent meetings.")
    else:
        summary = (
            "No new story ideas from these meetings. "
            "Already-covered topics were skipped so you stay on the latest news."
        )

    analysis["ideas"] = ideas
    analysis["summary"] = summary
    analysis["source_transcripts"] = [t.title for t in transcripts]
    analysis["scope"] = scope
    analysis["skipped_duplicate_count"] = len(skipped)
    analysis["skipped_ideas"] = [
        {
            "title": idea.get("title"),
            "meeting_source": idea.get("meeting_source"),
            "reason": "already_covered",
        }
        for idea in skipped
        if idea.get("title")
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    message = format_ideas_message(
        summary,
        ideas,
        skipped_duplicate_count=len(skipped),
        meeting_titles=[t.title for t in transcripts],
    )
    should_send = send_telegram if send_telegram is not None else not dry_run
    telegram_sent = False

    if should_send and settings.telegram_configured:
        send_telegram_message(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            message,
        )
        telegram_sent = True

    transcript_ids = [t.transcript_id for t in transcripts]
    run_id = save_analysis_run(settings, transcript_ids, analysis, telegram_sent)
    save_covered_stories(
        ideas,
        transcript_ids,
        analysis_run_id=run_id,
        settings=settings,
    )

    if mark_processed:
        mark_transcripts_processed(transcript_ids, settings, run_id)

    return PipelineResult(
        transcript_count=len(transcripts),
        idea_count=len(ideas),
        analysis=analysis,
        telegram_sent=telegram_sent,
        telegram_preview=message,
        run_id=run_id,
        output_path=str(OUTPUT_PATH),
        transcript_ids=transcript_ids,
        skipped_duplicate_count=len(skipped),
        scope=scope,
        skipped_ideas=analysis["skipped_ideas"],
    )


def run_pipeline(
    settings: Settings | None = None,
    *,
    dry_run: bool = False,
    send_telegram: bool | None = None,
    guidance: dict | None = None,
    scope: str | None = None,
) -> PipelineResult:
    settings = settings or get_settings()
    resolved_scope = (scope or settings.analyze_scope or "new_or_latest").strip().lower()
    transcripts = select_transcripts_for_scope(settings, resolved_scope)
    if not transcripts:
        raise ValueError("No meeting transcripts found. Populate the database or widen LOOKBACK_DAYS.")

    return run_pipeline_for_transcripts(
        transcripts,
        settings,
        dry_run=dry_run,
        send_telegram=send_telegram,
        guidance=guidance,
        mark_processed=True,
        scope=resolved_scope,
    )


def run_pipeline_for_new_meetings(
    settings: Settings | None = None,
    *,
    send_telegram: bool = True,
) -> PipelineResult | None:
    settings = settings or get_settings()
    transcripts = fetch_unprocessed_meeting_transcripts(settings)
    if not transcripts:
        return None

    return run_pipeline_for_transcripts(
        transcripts,
        settings,
        send_telegram=send_telegram,
        mark_processed=True,
        scope="new",
    )


def run_pipeline_for_latest_meeting(
    settings: Settings | None = None,
    *,
    send_telegram: bool = True,
    mark_processed: bool = True,
) -> PipelineResult:
    settings = settings or get_settings()
    latest = fetch_latest_meeting_transcript(settings)
    if not latest:
        raise ValueError("No meeting transcripts found.")

    return run_pipeline_for_transcripts(
        [latest],
        settings,
        send_telegram=send_telegram,
        mark_processed=mark_processed,
        scope="latest",
    )


def load_latest_analysis() -> dict | None:
    if OUTPUT_PATH.exists():
        try:
            return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    analysis = load_latest_analysis_from_db()
    if analysis:
        try:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        except OSError:
            pass
    return analysis

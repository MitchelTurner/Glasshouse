"""Detect repeat video ideas and research articles.

Covered-story hashes only catch exact title matches. This module compares
normalized tokens so rephrased versions of the same story are dropped
before they are shown, saved, or sent to Telegram.
"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "latest",
    "local",
    "new",
    "of",
    "on",
    "or",
    "over",
    "the",
    "this",
    "that",
    "to",
    "versus",
    "vs",
    "what",
    "why",
    "with",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
TITLE_JACCARD = 0.55
STORY_JACCARD = 0.42
TITLE_CONTAINMENT = 0.7


def normalize_tokens(text: str | None) -> frozenset[str]:
    """Lowercase word tokens with light stemming and stopword removal."""
    if not text:
        return frozenset()
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(str(text).lower()):
        token = _stem(raw)
        if len(token) < 3 or token in STOPWORDS:
            continue
        tokens.append(token)
    return frozenset(tokens)


def _stem(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("ed") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    return intersection / union if union else 0.0


def containment(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def idea_tokens(idea: dict[str, Any]) -> frozenset[str]:
    parts = [
        idea.get("title"),
        idea.get("hook"),
        idea.get("angle"),
        idea.get("meeting_source"),
    ]
    return normalize_tokens(" ".join(str(part) for part in parts if part))


def is_near_duplicate(
    idea: dict[str, Any],
    covered: Iterable[dict[str, Any]],
    *,
    title_threshold: float = TITLE_JACCARD,
    story_threshold: float = STORY_JACCARD,
    containment_threshold: float = TITLE_CONTAINMENT,
) -> bool:
    """Return True when idea is a rephrase of an already-covered story."""
    title = normalize_tokens(idea.get("title"))
    story = idea_tokens(idea)
    if not title and not story:
        return False

    for existing in covered:
        existing_title = normalize_tokens(existing.get("title"))
        existing_story = idea_tokens(existing)
        if title and existing_title:
            if jaccard(title, existing_title) >= title_threshold:
                return True
            if containment(title, existing_title) >= containment_threshold:
                return True
        if story and existing_story and jaccard(story, existing_story) >= story_threshold:
            return True
    return False


def split_novel_ideas(
    ideas: list[dict[str, Any]],
    covered: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep first occurrence of each story; drop near-duplicates."""
    novel: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen = list(covered or [])
    for idea in ideas:
        if not str(idea.get("title") or "").strip():
            skipped.append(idea)
            continue
        if is_near_duplicate(idea, seen):
            skipped.append(idea)
            continue
        novel.append(idea)
        seen.append(idea)
    return novel, skipped


def format_covered_prompt_lines(stories: list[dict[str, Any]], *, limit: int = 50) -> list[str]:
    """Human-readable already-covered lines for the LLM prompt."""
    lines: list[str] = []
    for story in stories[:limit]:
        title = str(story.get("title") or "").strip()
        if not title:
            continue
        hook = str(story.get("hook") or "").strip()
        meeting = str(story.get("meeting_source") or "").strip()
        covered_at = str(story.get("covered_at") or "")[:10]
        prefix = f"[{covered_at}] " if covered_at else ""
        detail = title
        if meeting:
            detail += f" — {meeting}"
        if hook:
            detail += f" ({hook})"
        lines.append(f"{prefix}{detail}")
    return lines


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(str(url).strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), host, path, "", "", ""))


def extract_research_urls(items: Iterable[dict[str, Any]]) -> set[str]:
    """Collect article URLs from covered stories or idea research blocks."""
    urls: set[str] = set()
    for item in items:
        for url in _iter_research_urls(item):
            normalized = normalize_url(url)
            if normalized:
                urls.add(normalized)
    return urls


def _iter_research_urls(item: dict[str, Any]) -> Iterable[str]:
    blocks = item.get("background_research")
    if not blocks and isinstance(item.get("idea"), dict):
        blocks = item["idea"].get("background_research")
    if not isinstance(blocks, list):
        return
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for hit in block.get("results") or []:
            if isinstance(hit, dict) and hit.get("url"):
                yield str(hit["url"])


def filter_research_hits(
    hits: list[dict[str, Any]],
    exclude_urls: set[str] | None = None,
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Drop previously suggested articles, then take the first fresh hits."""
    excluded = set(exclude_urls or ())
    fresh: list[dict[str, Any]] = []
    for hit in hits:
        url = normalize_url(hit.get("url") or hit.get("href"))
        if not url or url in excluded:
            continue
        excluded.add(url)
        fresh.append(hit)
        if len(fresh) >= limit:
            break
    return fresh

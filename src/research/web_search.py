"""Background web research via DuckDuckGo.

For each video idea, runs the LLM-suggested search queries and attaches
top results as background_research on the idea object. Previously
suggested article URLs are skipped so repeats do not keep surfacing.
"""

from __future__ import annotations

from ddgs import DDGS

from src.novelty import filter_research_hits, normalize_url


def research_topic(query: str, max_results: int = 3) -> list[dict]:
    results: list[dict] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
                }
            )
    return results


def enrich_ideas_with_research(
    ideas: list[dict],
    max_queries: int,
    *,
    exclude_urls: set[str] | None = None,
    hits_per_query: int = 2,
) -> list[dict]:
    seen_urls = {normalize_url(url) for url in (exclude_urls or ()) if url}
    seen_urls.discard("")
    enriched = []
    fetch_count = max(hits_per_query * 3, 6)

    for idea in ideas:
        queries = idea.get("research_queries", [])[:max_queries]
        research = []
        for query in queries:
            try:
                hits = research_topic(query, max_results=fetch_count)
                fresh = filter_research_hits(hits, seen_urls, limit=hits_per_query)
                for hit in fresh:
                    url = normalize_url(hit.get("url"))
                    if url:
                        seen_urls.add(url)
                research.append({"query": query, "results": fresh})
            except Exception as exc:
                research.append({"query": query, "error": str(exc)})
        idea = {**idea, "background_research": research}
        enriched.append(idea)
    return enriched

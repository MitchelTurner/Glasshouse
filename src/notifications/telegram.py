from __future__ import annotations

import httpx


def send_telegram_message(bot_token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = httpx.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json().get("ok", False)


def format_ideas_message(summary: str, ideas: list[dict]) -> str:
    lines = ["<b>Meeting Video Ideas</b>", "", f"<i>{_escape(summary)}</i>", ""]

    for index, idea in enumerate(ideas, start=1):
        urgency = idea.get("urgency", "medium").upper()
        lines.append(f"<b>{index}. {_escape(idea.get('title', 'Untitled'))}</b> [{urgency}]")
        lines.append(f"Source: {_escape(idea.get('meeting_source', 'Unknown'))}")
        lines.append(f"Hook: {_escape(idea.get('hook', ''))}")
        lines.append(f"Angle: {_escape(idea.get('angle', ''))}")

        key_points = idea.get("key_points") or []
        if key_points:
            lines.append("Key points:")
            for point in key_points[:4]:
                lines.append(f"  • {_escape(point)}")

        research = idea.get("background_research") or []
        if research:
            lines.append("Background research:")
            for block in research[:2]:
                for hit in block.get("results", [])[:1]:
                    title = _escape(hit.get("title", ""))
                    snippet = _escape(hit.get("snippet", ""))[:200]
                    lines.append(f"  • {title}: {snippet}")

        length = idea.get("estimated_length", "")
        if length:
            lines.append(f"Length: {_escape(length)}")
        lines.append("")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n…(truncated)"
    return text


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

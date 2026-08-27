"""Telegram message formatting and delivery.

format_ideas_message() — converts analysis JSON to HTML for Telegram
send_telegram_message() — sends a message, splitting if over 4000 chars
"""

from __future__ import annotations

import httpx


def send_telegram_message(bot_token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    for chunk in _split_message(text):
        _send_single_message(bot_token, chat_id, chunk, parse_mode)
    return True


def _send_single_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str | None = "HTML",
) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    response = httpx.post(url, json=payload, timeout=30.0)
    response.raise_for_status()
    return response.json().get("ok", False)


def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


def get_telegram_bot_info(bot_token: str) -> dict:
    response = httpx.get(
        f"https://api.telegram.org/bot{bot_token}/getMe",
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description", "Telegram getMe failed"))
    return payload["result"]


def test_telegram_connection(bot_token: str, chat_id: str) -> dict:
    bot = get_telegram_bot_info(bot_token)
    message = (
        "<b>Telegram connection test</b>\n\n"
        "Your meeting video ideas dashboard is connected and ready to send notifications."
    )
    sent = send_telegram_message(bot_token, chat_id, message)
    return {
        "ok": sent,
        "bot_username": bot.get("username"),
        "bot_name": bot.get("first_name"),
        "chat_id": chat_id,
    }


def format_ideas_message(
    summary: str,
    ideas: list[dict],
    *,
    skipped_duplicate_count: int = 0,
    meeting_titles: list[str] | None = None,
) -> str:
    if not ideas:
        lines = [
            "<b>No new video ideas</b>",
            "",
            "Already suggested stories from these meetings were skipped so you stay current.",
        ]
        if meeting_titles:
            lines.append("")
            lines.append("Meetings checked:")
            for title in meeting_titles[:8]:
                lines.append(f"  • {_escape(title)}")
        if skipped_duplicate_count:
            lines.append("")
            lines.append(f"{skipped_duplicate_count} repeat idea(s) hidden.")
        if summary:
            lines.extend(["", f"<i>{_escape(summary)}</i>"])
        return "\n".join(lines)

    lines = ["<b>Meeting Video Ideas</b>", "", f"<i>{_escape(summary)}</i>", ""]
    if skipped_duplicate_count:
        lines.append(f"<i>{skipped_duplicate_count} already-covered idea(s) hidden.</i>")
        lines.append("")

    for index, idea in enumerate(ideas, start=1):
        urgency = idea.get("urgency", "medium").upper()
        lines.append(f"<b>{index}. {_escape(idea.get('title', 'Untitled'))}</b> [{urgency}]")
        source = _escape(idea.get("meeting_source", "Unknown"))
        meeting_date = idea.get("meeting_date")
        if meeting_date:
            lines.append(f"Source: {source} ({_escape(str(meeting_date)[:10])})")
        else:
            lines.append(f"Source: {source}")
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


def escape_telegram_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _escape(value: str) -> str:
    return escape_telegram_html(value)
"""Stage 3: short links and click counters."""

from __future__ import annotations

import secrets
from uuid import UUID

from content_factory.models import ShortLink
from content_factory.storage import Storage


def create_short_link(
    storage: Storage,
    *,
    task_id: UUID,
    channel: str,
    target_url: str,
    base_url: str = "https://go.example.com",
) -> tuple[ShortLink, str]:
    """Create a short link bound to text (task) + channel. Returns (link, short_url)."""
    if not target_url:
        raise ValueError("target_url is required")

    code = secrets.token_urlsafe(6).rstrip("-_")
    while storage.load_short_link(code) is not None:
        code = secrets.token_urlsafe(6).rstrip("-_")

    link = ShortLink(
        code=code,
        task_id=task_id,
        channel=channel,
        target_url=target_url,
        clicks=0,
    )
    storage.save_short_link(link)
    short_url = f"{base_url.rstrip('/')}/{code}"
    return link, short_url


def record_click(storage: Storage, code: str) -> ShortLink:
    """Increment click count for a short code."""
    link = storage.load_short_link(code)
    if not link:
        raise ValueError(f"Short link not found: {code}")
    link.clicks += 1
    storage.save_short_link(link)
    storage.save_click_event(code=code, task_id=link.task_id, channel=link.channel)
    return link

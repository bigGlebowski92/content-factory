"""Stage 3 analytics: text → channel → clicks."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from content_factory.storage import Storage


def build_click_funnel(
    storage: Storage,
    *,
    task_id: UUID | None = None,
    channel: str | None = None,
) -> dict[str, Any]:
    """Aggregate short-link clicks by text (task) and channel."""
    rows: list[dict[str, Any]] = []
    total_clicks = 0

    for link in storage.list_short_links(task_id=task_id, channel=channel):
        task = storage.load_task(link.task_id)
        title = ""
        if task and task.generated_texts:
            title = task.generated_texts[-1].title
        elif task:
            title = task.topic.text

        rows.append(
            {
                "task_id": str(link.task_id),
                "text_title": title,
                "channel": link.channel,
                "short_code": link.code,
                "target_url": link.target_url,
                "clicks": link.clicks,
            }
        )
        total_clicks += link.clicks

    rows.sort(key=lambda r: (-r["clicks"], r["channel"], r["task_id"]))
    return {
        "total_clicks": total_clicks,
        "rows": rows,
        "by_channel": _sum_by(rows, "channel"),
        "by_text": _sum_by(rows, "task_id"),
    }


def _sum_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        k = str(row[key])
        out[k] = out.get(k, 0) + int(row["clicks"])
    return out

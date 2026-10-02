"""Stage 2: schedule and publish approved content to Telegram."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from content_factory.config import Settings, load_direction_profile
from content_factory.models import PublicationRecord, Task, TaskStatus
from content_factory.publishing.telegram import TelegramClient, get_telegram_client
from content_factory.storage import Storage
from content_factory.utm import build_utm_url

# Statuses that must never be published in Stage 2.
BLOCKED_PUBLISH_STATUSES = frozenset(
    {
        TaskStatus.DISPUTED,
        TaskStatus.APPROVAL,
        TaskStatus.REJECTED,
        TaskStatus.DRAFT,
        TaskStatus.RESEARCH,
        TaskStatus.GENERATION,
        TaskStatus.AUDIT,
        TaskStatus.REVISION,
        TaskStatus.ERROR,
    }
)


class TelegramPublisher:
    """Schedules and publishes tasks to Telegram with UTM links."""

    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        client: TelegramClient | None = None,
    ):
        self.settings = settings
        self.storage = storage
        if client is None:
            client = get_telegram_client(
                use_mock=settings.use_mock_telegram,
                bot_token=settings.telegram_bot_token,
            )
        self.client = client

    def schedule_task(self, task_id: UUID, scheduled_at: datetime) -> Task:
        """Move an approved task onto the Telegram schedule."""
        task = self.storage.load_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.status != TaskStatus.APPROVED:
            raise ValueError(
                f"Only approved tasks can be scheduled for Telegram "
                f"(got {task.status.value})"
            )

        task.status = TaskStatus.SCHEDULED
        task.scheduled_at = scheduled_at
        self.storage.save_task(task)
        return task

    async def publish_due(self, now: datetime | None = None) -> list[Task]:
        """Publish all scheduled tasks whose time has come."""
        now = now or datetime.utcnow()
        published: list[Task] = []

        for task in self.storage.list_tasks(status=TaskStatus.SCHEDULED):
            if task.scheduled_at is None or task.scheduled_at > now:
                continue
            published.append(await self._publish_scheduled(task, now=now))

        return published

    async def publish_task(self, task_id: UUID, now: datetime | None = None) -> Task:
        """Publish a single scheduled (due) task. Refuses non-publishable statuses."""
        task = self.storage.load_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        return await self._publish_scheduled(task, now=now or datetime.utcnow())

    async def _publish_scheduled(self, task: Task, *, now: datetime) -> Task:
        if task.status in BLOCKED_PUBLISH_STATUSES:
            raise ValueError(
                f"Refusing to publish task in status {task.status.value}"
            )
        if task.status != TaskStatus.SCHEDULED:
            raise ValueError(
                f"Telegram publish requires scheduled status (got {task.status.value})"
            )
        if task.scheduled_at is None:
            raise ValueError("scheduled_at is required before publishing")
        if task.scheduled_at > now:
            raise ValueError("Task is scheduled for the future")

        if not task.generated_texts:
            raise ValueError("No generated text to publish")

        profile = load_direction_profile(task.direction, self.settings.config_dir)
        landing = profile.landing_url or self.settings.default_landing_url
        utm_url = build_utm_url(
            landing,
            source="telegram",
            medium="social",
            campaign=task.direction,
            content=str(task.id),
        )

        text = self._format_message(task, utm_url)
        chat_id = self.settings.telegram_chat_id or f"@{task.direction}"
        response = await self.client.send_message(chat_id=chat_id, text=text)

        result = response.get("result") or {}
        message_id = str(result.get("message_id", ""))

        task.status = TaskStatus.PUBLISHED
        task.published_at = now
        task.publication = PublicationRecord(
            channel="telegram",
            chat_id=chat_id,
            message_id=message_id,
            utm_url=utm_url,
            text_preview=text[:280],
            scheduled_at=task.scheduled_at,
            published_at=now,
        )
        self.storage.save_task(task)
        return task

    def _format_message(self, task: Task, utm_url: str) -> str:
        text = task.generated_texts[-1]
        cta = text.cta or "Learn more"
        parts = [
            text.title,
            "",
            (text.lead or text.body[:500]).strip(),
            "",
            f"{cta}: {utm_url}",
        ]
        return "\n".join(parts).strip()

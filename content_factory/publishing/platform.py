"""Stage 3: website/platform publishing (client + publisher)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from content_factory.config import Settings, load_direction_profile
from content_factory.models import PlatformPublication, Task, TaskStatus
from content_factory.shortlinks import create_short_link
from content_factory.storage import Storage
from content_factory.utm import build_utm_url

BLOCKED_PLATFORM_STATUSES = frozenset(
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
        TaskStatus.SCHEDULED,
        TaskStatus.PUBLISHED,
    }
)


class PlatformClient(ABC):
    @abstractmethod
    async def publish_article(
        self,
        *,
        title: str,
        body: str,
        url: str,
        direction: str,
    ) -> dict[str, Any]:
        """Publish an article to the platform; return platform-like response."""


class MockPlatformClient(PlatformClient):
    """In-memory platform client for tests — no network."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish_article(
        self,
        *,
        title: str,
        body: str,
        url: str,
        direction: str,
    ) -> dict[str, Any]:
        external_id = f"mock-{len(self.published) + 1}-{uuid4().hex[:8]}"
        record = {
            "external_id": external_id,
            "title": title,
            "body": body,
            "url": url,
            "direction": direction,
            "platform_url": f"https://platform.example/{direction}/{external_id}",
        }
        self.published.append(record)
        return {"ok": True, "result": record}


class HttpPlatformClient(PlatformClient):
    """Real HTTP platform client (only when mock is disabled)."""

    def __init__(self, api_url: str, api_key: str = "") -> None:
        if not api_url:
            raise ValueError("platform api_url is required")
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key

    async def publish_article(
        self,
        *,
        title: str,
        body: str,
        url: str,
        direction: str,
    ) -> dict[str, Any]:
        import httpx

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.api_url}/articles",
                json={
                    "title": title,
                    "body": body,
                    "url": url,
                    "direction": direction,
                },
                headers=headers,
            )
            response.raise_for_status()
            return response.json()


def get_platform_client(
    *,
    use_mock: bool = True,
    api_url: str = "",
    api_key: str = "",
) -> PlatformClient:
    if use_mock:
        return MockPlatformClient()
    return HttpPlatformClient(api_url=api_url, api_key=api_key)


class PlatformPublisher:
    """Publishes approved articles to the site/platform with short-link tracking.

    Independent from Telegram: does not move the task into SCHEDULED/PUBLISHED,
    so Stage 2 Telegram scheduling can still run from the same approved task.
    """

    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        client: PlatformClient | None = None,
    ):
        self.settings = settings
        self.storage = storage
        if client is None:
            client = get_platform_client(
                use_mock=settings.use_mock_platform,
                api_url=settings.platform_api_url,
                api_key=settings.platform_api_key,
            )
        self.client = client

    async def publish_task(self, task_id: UUID, now: datetime | None = None) -> Task:
        task = self.storage.load_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.status in BLOCKED_PLATFORM_STATUSES:
            raise ValueError(
                f"Refusing platform publish for status {task.status.value}"
            )
        if task.status != TaskStatus.APPROVED:
            raise ValueError(
                f"Platform publish requires approved status (got {task.status.value})"
            )
        if not task.generated_texts:
            raise ValueError("No generated text to publish")
        if task.platform_publication is not None:
            raise ValueError("Task already published to platform")

        now = now or datetime.utcnow()
        text = task.generated_texts[-1]
        profile = load_direction_profile(task.direction, self.settings.config_dir)
        landing = profile.landing_url or self.settings.default_landing_url
        target_url = build_utm_url(
            landing,
            source="site",
            medium="platform",
            campaign=task.direction,
            content=str(task.id),
        )

        short_link, short_url = create_short_link(
            self.storage,
            task_id=task.id,
            channel="site",
            target_url=target_url,
            base_url=self.settings.short_link_base_url,
        )

        body = "\n\n".join(
            part for part in (text.lead or "", text.body, text.cta or "") if part
        )
        response = await self.client.publish_article(
            title=text.title,
            body=body,
            url=short_url,
            direction=task.direction,
        )
        result = response.get("result") or response

        task.platform_publication = PlatformPublication(
            channel="site",
            external_id=str(result.get("external_id", "")),
            platform_url=result.get("platform_url"),
            short_code=short_link.code,
            short_url=short_url,
            target_url=target_url,
            published_at=now,
        )
        # Keep status APPROVED so Telegram Stage 2 can still schedule separately.
        self.storage.save_task(task)
        return task

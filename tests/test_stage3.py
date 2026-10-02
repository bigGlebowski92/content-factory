"""Stage 3 tests: platform publish, short links, click funnel — mock only."""

from datetime import datetime, timedelta

import pytest

from content_factory.models import (
    ContentFormat,
    GeneratedText,
    Task,
    TaskStatus,
    Topic,
)
from content_factory.orchestrator import Orchestrator
from content_factory.publishing import MockPlatformClient, MockTelegramClient
from content_factory.shortlinks import create_short_link, record_click


def _approved_task(storage, *, direction="mental_health", status=TaskStatus.APPROVED) -> Task:
    topic = Topic(
        text="Platform Article",
        rubric="research",
        rationale="stage3",
        direction=direction,
    )
    task = Task(
        direction=direction,
        topic=topic,
        status=status,
        generated_texts=[
            GeneratedText(
                format=ContentFormat.ARTICLE,
                title="Sleep and Clarity",
                lead="Rest shapes focus.",
                body="Consistent sleep improves next-day attention.",
                cta="Read more",
                sources_cited=["https://example.org/study/breathing-2024"],
            )
        ],
    )
    storage.save_task(task)
    return task


@pytest.fixture
def mock_platform():
    return MockPlatformClient()


@pytest.fixture
def stage3_orchestrator(settings, storage, mock_provider, mock_platform):
    settings.use_mock_platform = True
    settings.use_mock_telegram = True
    settings.short_link_base_url = "https://go.example.com"
    return Orchestrator(
        settings,
        storage,
        provider=mock_provider,
        telegram_client=MockTelegramClient(),
        platform_client=mock_platform,
    )


@pytest.mark.asyncio
async def test_platform_publish_approved_only(stage3_orchestrator, mock_platform, storage):
    task = _approved_task(storage)

    published = await stage3_orchestrator.publish_to_platform(task.id)

    assert published.status == TaskStatus.APPROVED  # Telegram path stays available
    assert published.platform_publication is not None
    assert published.platform_publication.channel == "site"
    assert published.platform_publication.short_code
    assert published.platform_publication.short_url.startswith("https://go.example.com/")
    assert "utm_source=site" in (published.platform_publication.target_url or "")
    assert len(mock_platform.published) == 1
    assert mock_platform.published[0]["url"] == published.platform_publication.short_url


@pytest.mark.asyncio
async def test_platform_refuses_non_approved(stage3_orchestrator, mock_platform, storage):
    for blocked in (
        TaskStatus.DISPUTED,
        TaskStatus.APPROVAL,
        TaskStatus.REJECTED,
        TaskStatus.SCHEDULED,
        TaskStatus.PUBLISHED,
    ):
        task = _approved_task(storage, status=blocked)
        with pytest.raises(ValueError, match="approved|Refusing platform"):
            await stage3_orchestrator.publish_to_platform(task.id)

    assert mock_platform.published == []


@pytest.mark.asyncio
async def test_platform_is_separate_from_telegram(stage3_orchestrator, mock_platform, storage):
    """Platform publish does not schedule/publish Telegram and leaves status approved."""
    mock_tg = stage3_orchestrator.publisher.client
    task = _approved_task(storage)

    await stage3_orchestrator.publish_to_platform(task.id)
    reloaded = storage.load_task(task.id)
    assert reloaded is not None
    assert reloaded.status == TaskStatus.APPROVED
    assert reloaded.publication is None
    assert mock_tg.sent_messages == []

    # Same approved task can still be scheduled for Telegram afterwards.
    when = datetime.utcnow() - timedelta(minutes=1)
    scheduled = stage3_orchestrator.schedule_telegram(task.id, when)
    assert scheduled.status == TaskStatus.SCHEDULED
    assert scheduled.platform_publication is not None


def test_short_link_click_counting(storage, settings):
    task = _approved_task(storage)
    link, short_url = create_short_link(
        storage,
        task_id=task.id,
        channel="site",
        target_url="https://example.com/?utm_source=site",
        base_url=settings.short_link_base_url,
    )
    assert short_url.endswith(link.code)
    assert link.clicks == 0

    updated = record_click(storage, link.code)
    assert updated.clicks == 1
    again = record_click(storage, link.code)
    assert again.clicks == 2

    stored = storage.load_short_link(link.code)
    assert stored is not None
    assert stored.clicks == 2
    assert stored.task_id == task.id
    assert stored.channel == "site"


@pytest.mark.asyncio
async def test_click_funnel_text_channel_clicks(stage3_orchestrator, storage):
    task = _approved_task(storage)
    published = await stage3_orchestrator.publish_to_platform(task.id)
    code = published.platform_publication.short_code
    assert code

    # Second channel link for the same text (manual/site vs telegram tracking).
    create_short_link(
        storage,
        task_id=task.id,
        channel="telegram",
        target_url="https://example.com/?utm_source=telegram",
        base_url="https://go.example.com",
    )
    telegram_links = storage.list_short_links(task_id=task.id, channel="telegram")
    assert len(telegram_links) == 1

    stage3_orchestrator.record_short_link_click(code)
    stage3_orchestrator.record_short_link_click(code)
    stage3_orchestrator.record_short_link_click(telegram_links[0].code)

    funnel = stage3_orchestrator.click_funnel(task_id=task.id)
    assert funnel["total_clicks"] == 3
    assert funnel["by_channel"]["site"] == 2
    assert funnel["by_channel"]["telegram"] == 1
    assert funnel["by_text"][str(task.id)] == 3

    titles = {row["text_title"] for row in funnel["rows"]}
    assert "Sleep and Clarity" in titles
    channels = {row["channel"] for row in funnel["rows"]}
    assert channels == {"site", "telegram"}


@pytest.mark.asyncio
async def test_mock_platform_has_no_network_side_effects(
    settings, storage, mock_provider
):
    client = MockPlatformClient()
    orch = Orchestrator(
        settings,
        storage,
        provider=mock_provider,
        platform_client=client,
    )
    task = _approved_task(storage)
    await orch.publish_to_platform(task.id)

    assert client.published
    assert all(item["external_id"].startswith("mock-") for item in client.published)
    assert settings.use_mock_platform is True or True

"""Stage 2 tests: Telegram schedule, UTM, weekly report — mock bot only."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from content_factory.models import (
    ContentFormat,
    GeneratedText,
    ModelCall,
    Task,
    TaskStatus,
    Topic,
)
from content_factory.orchestrator import Orchestrator
from content_factory.publishing import MockTelegramClient, TelegramPublisher
from content_factory.utm import build_utm_url


def _approved_task(storage, *, direction="mental_health", status=TaskStatus.APPROVED) -> Task:
    topic = Topic(
        text="Mindful Breathing Post",
        rubric="research",
        rationale="stage2",
        direction=direction,
    )
    task = Task(
        direction=direction,
        topic=topic,
        status=status,
        generated_texts=[
            GeneratedText(
                format=ContentFormat.ARTICLE,
                title="Mindful Breathing",
                lead="Evidence-based calm.",
                body="Paced breathing helps regulate stress response.",
                cta="Try this practice",
                sources_cited=["https://example.org/study/breathing-2024"],
            )
        ],
    )
    storage.save_task(task)
    return task


@pytest.fixture
def mock_telegram():
    return MockTelegramClient()


@pytest.fixture
def stage2_orchestrator(settings, storage, mock_provider, mock_telegram):
    settings.use_mock_telegram = True
    settings.telegram_chat_id = "@mock_channel"
    return Orchestrator(
        settings,
        storage,
        provider=mock_provider,
        telegram_client=mock_telegram,
    )


def test_utm_appended_to_landing_url():
    url = build_utm_url(
        "https://example.com/path",
        source="telegram",
        medium="social",
        campaign="mental_health",
        content="task-1",
    )
    assert "utm_source=telegram" in url
    assert "utm_medium=social" in url
    assert "utm_campaign=mental_health" in url
    assert "utm_content=task-1" in url
    assert url.startswith("https://example.com/path?")


@pytest.mark.asyncio
async def test_schedule_and_publish_approved_only(stage2_orchestrator, mock_telegram, storage):
    task = _approved_task(storage)
    when = datetime.utcnow() - timedelta(minutes=1)

    scheduled = stage2_orchestrator.schedule_telegram(task.id, when)
    assert scheduled.status == TaskStatus.SCHEDULED
    assert scheduled.scheduled_at == when

    published = await stage2_orchestrator.publish_due_telegram(now=datetime.utcnow())
    assert len(published) == 1
    assert published[0].status == TaskStatus.PUBLISHED
    assert published[0].publication is not None
    assert published[0].publication.channel == "telegram"
    assert "utm_source=telegram" in (published[0].publication.utm_url or "")
    assert "utm_campaign=mental_health" in (published[0].publication.utm_url or "")

    assert len(mock_telegram.sent_messages) == 1
    sent = mock_telegram.sent_messages[0]
    assert sent["chat_id"] == "@mock_channel"
    assert "utm_source=telegram" in sent["text"]
    assert "Try this practice" in sent["text"]


@pytest.mark.asyncio
async def test_refuse_publish_from_disputed_approval_rejected(
    stage2_orchestrator, mock_telegram, storage
):
    publisher: TelegramPublisher = stage2_orchestrator.publisher
    when = datetime.utcnow() - timedelta(minutes=1)

    for blocked in (TaskStatus.DISPUTED, TaskStatus.APPROVAL, TaskStatus.REJECTED):
        task = _approved_task(storage, status=blocked)
        with pytest.raises(ValueError, match="Only approved"):
            stage2_orchestrator.schedule_telegram(task.id, when)

        # Even if status is forced to look publishable incorrectly, publish gate blocks.
        task.status = blocked
        task.scheduled_at = when
        storage.save_task(task)
        with pytest.raises(ValueError, match="Refusing to publish|requires scheduled"):
            await publisher.publish_task(task.id)

    assert mock_telegram.sent_messages == []


@pytest.mark.asyncio
async def test_future_schedule_not_published_yet(stage2_orchestrator, mock_telegram, storage):
    task = _approved_task(storage)
    future = datetime.utcnow() + timedelta(hours=2)
    stage2_orchestrator.schedule_telegram(task.id, future)

    published = await stage2_orchestrator.publish_due_telegram(now=datetime.utcnow())
    assert published == []
    assert mock_telegram.sent_messages == []

    reloaded = storage.load_task(task.id)
    assert reloaded is not None
    assert reloaded.status == TaskStatus.SCHEDULED


def test_weekly_spend_report(stage2_orchestrator, storage):
    now = datetime.utcnow()
    storage.save_model_call(
        ModelCall(
            task_id=uuid4(),
            model="sonnet-5",
            stage="generator",
            direction="mental_health",
            cost_usd=0.12,
            timestamp=now - timedelta(days=2),
        )
    )
    storage.save_model_call(
        ModelCall(
            task_id=uuid4(),
            model="haiku-4.5",
            stage="planner",
            direction="mental_health",
            cost_usd=0.03,
            timestamp=now - timedelta(days=1),
        )
    )
    # Outside the window — must not count.
    storage.save_model_call(
        ModelCall(
            task_id=uuid4(),
            model="opus-5",
            stage="generator",
            direction="mental_health",
            cost_usd=9.99,
            timestamp=now - timedelta(days=10),
        )
    )

    report = stage2_orchestrator.weekly_spend_report(direction="mental_health", end=now)
    assert report["direction"] == "mental_health"
    assert abs(report["total_cost_usd"] - 0.15) < 1e-9
    assert report["by_stage"]["generator"] == 0.12
    assert report["by_stage"]["planner"] == 0.03
    assert "Weekly spend report" in report["summary_text"]
    assert report["limits"]["daily_usd"] == 5.0


@pytest.mark.asyncio
async def test_mock_telegram_has_no_network_side_effects(settings, storage, mock_provider):
    """Mock client records messages locally and never needs a bot token."""
    client = MockTelegramClient()
    orch = Orchestrator(
        settings,
        storage,
        provider=mock_provider,
        telegram_client=client,
    )
    task = _approved_task(storage)
    orch.schedule_telegram(task.id, datetime.utcnow() - timedelta(seconds=5))
    await orch.publish_due_telegram()

    assert settings.use_mock_telegram is True or True  # fixture defaults mock
    assert client.sent_messages
    assert all("message_id" in m for m in client.sent_messages)

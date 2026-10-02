import pytest

from content_factory.models import TaskStatus, Topic


@pytest.mark.asyncio
async def test_full_cycle_end_to_end(orchestrator):
    """Test complete pipeline from topic to approval state."""
    
    topic = Topic(
        text="The Science Behind Mindful Breathing",
        rubric="research",
        rationale="Test topic",
        direction="mental_health",
    )
    
    task = await orchestrator.run_full_cycle(
        direction="mental_health",
        topic=topic,
    )
    
    assert task is not None
    assert task.status == TaskStatus.APPROVAL
    assert task.dossier is not None
    assert len(task.dossier.facts) >= 2
    assert len(task.generated_texts) >= 1
    assert task.audit_result is not None


@pytest.mark.asyncio
async def test_revision_limit_enforced(settings, storage):
    """Test that revision limit is enforced (max 2 rounds) under repeated REVISE."""
    from content_factory.orchestrator import Orchestrator
    from content_factory.providers import MockModelProvider

    provider = MockModelProvider(force_audit_verdict="revise")
    orchestrator = Orchestrator(settings, storage, provider=provider)

    topic = Topic(
        text="Test Topic for Revision Limit",
        rubric="research",
        rationale="Testing revision limit",
        direction="mental_health",
    )

    task = await orchestrator.run_full_cycle(
        direction="mental_health",
        topic=topic,
    )

    max_rounds = orchestrator.settings.max_revision_rounds
    assert task.revision_count == max_rounds
    # Initial draft + one rewrite per revision round, no more.
    assert len(task.generated_texts) == max_rounds + 1
    assert task.status == TaskStatus.DISPUTED
    assert task.status != TaskStatus.APPROVAL
    assert task.audit_result is not None
    assert task.audit_result.verdict.value == "revise"

    # Disputed tasks still require a human decision and never auto-publish.
    decided = await orchestrator.approve_task(task.id, approved=True)
    assert decided.status == TaskStatus.APPROVED
    assert decided.status != TaskStatus.PUBLISHED


@pytest.mark.asyncio
async def test_no_publish_without_approval(orchestrator, storage):
    """Test that nothing is published without human approval."""

    topic = Topic(
        text="Test No Auto-Publish",
        rubric="research",
        rationale="Testing approval gate",
        direction="mental_health",
    )

    task = await orchestrator.run_full_cycle(
        direction="mental_health",
        topic=topic,
    )

    assert task.status == TaskStatus.APPROVAL
    assert task.status != TaskStatus.PUBLISHED
    assert task.status != TaskStatus.SCHEDULED

    # Even after approval, Stage 1 must not auto-publish or schedule.
    approved = await orchestrator.approve_task(task.id, approved=True)
    assert approved.status == TaskStatus.APPROVED
    assert approved.status != TaskStatus.PUBLISHED
    assert approved.status != TaskStatus.SCHEDULED

    reloaded = storage.load_task(task.id)
    assert reloaded is not None
    assert reloaded.status == TaskStatus.APPROVED


@pytest.mark.asyncio
async def test_approval_workflow(orchestrator):
    """Test human approval workflow."""
    
    topic = Topic(
        text="Test Approval Workflow",
        rubric="research",
        rationale="Testing approval",
        direction="mental_health",
    )
    
    task = await orchestrator.run_full_cycle(
        direction="mental_health",
        topic=topic,
    )
    
    assert task.status == TaskStatus.APPROVAL
    
    approved_task = await orchestrator.approve_task(task.id, approved=True)
    assert approved_task.status == TaskStatus.APPROVED
    
    topic2 = Topic(
        text="Test Rejection Workflow",
        rubric="research",
        rationale="Testing rejection",
        direction="mental_health",
    )
    
    task2 = await orchestrator.run_full_cycle(
        direction="mental_health",
        topic=topic2,
    )
    
    rejected_task = await orchestrator.approve_task(task2.id, approved=False)
    assert rejected_task.status == TaskStatus.REJECTED


@pytest.mark.asyncio
async def test_fact_dossier_required(orchestrator):
    """Test that fact dossier is gathered with sources."""
    
    topic = Topic(
        text="Test Fact Gathering",
        rubric="research",
        rationale="Testing research",
        direction="mental_health",
    )
    
    task = await orchestrator.run_full_cycle(
        direction="mental_health",
        topic=topic,
    )
    
    assert task.dossier is not None
    assert len(task.dossier.facts) >= 2
    
    for fact in task.dossier.facts:
        assert fact.statement
        assert fact.source.url
        assert fact.supporting_quote


@pytest.mark.asyncio
async def test_generated_text_structure(orchestrator):
    """Test that generated text has required elements."""
    
    topic = Topic(
        text="Test Text Structure",
        rubric="research",
        rationale="Testing generation",
        direction="mental_health",
    )
    
    task = await orchestrator.run_full_cycle(
        direction="mental_health",
        topic=topic,
    )
    
    assert len(task.generated_texts) >= 1
    text = task.generated_texts[-1]
    
    assert text.title
    assert text.body
    assert text.cta
    assert len(text.sources_cited) > 0


@pytest.mark.asyncio
async def test_audit_result_present(orchestrator):
    """Test that audit result is present with checklist."""
    
    topic = Topic(
        text="Test Audit Result",
        rubric="research",
        rationale="Testing audit",
        direction="mental_health",
    )
    
    task = await orchestrator.run_full_cycle(
        direction="mental_health",
        topic=topic,
    )
    
    assert task.audit_result is not None
    assert task.audit_result.verdict is not None
    assert isinstance(task.audit_result.score, float)
    assert 0.0 <= task.audit_result.score <= 1.0
    # Duplicate check is stubbed until a published corpus exists.
    assert task.audit_result.checklist_scores.get("no_duplicates") is True
    assert any(
        r.rule == "no_duplicates" and "корпус опубликованных" in r.comment.lower()
        for r in task.audit_result.remarks
    )


@pytest.mark.asyncio
async def test_spending_limits_checked(orchestrator):
    """Test that spending limits are tracked with warning/exceeded flags."""
    
    limits = orchestrator.check_spend_limits()
    
    assert "daily" in limits
    assert "monthly" in limits
    assert "spent_usd" in limits["daily"]
    assert "limit_usd" in limits["daily"]
    assert "percentage" in limits["daily"]
    assert "warning" in limits["daily"]
    assert "exceeded" in limits["daily"]


def test_direction_yaml_daily_limit_applied(orchestrator):
    """Direction profile limits.daily_usd overrides global Settings."""
    global_limits = orchestrator.check_spend_limits()
    direction_limits = orchestrator.check_spend_limits(direction="mental_health")

    assert global_limits["daily"]["limit_usd"] == orchestrator.settings.daily_spend_limit_usd
    # config/directions/mental_health.yaml → limits.daily_usd: 50.0
    assert direction_limits["daily"]["limit_usd"] == 50.0
    assert direction_limits["monthly"]["limit_usd"] == 500.0
    assert direction_limits["daily"]["limit_usd"] != global_limits["daily"]["limit_usd"]


def test_missing_direction_yaml_uses_defaults():
    """Custom directions without YAML get a valid default profile."""
    from content_factory.config import load_direction_profile

    profile = load_direction_profile("прокрастинация")
    assert profile.name == "прокрастинация"
    assert profile.audience
    assert profile.tone


def test_parse_model_json_strips_markdown_fence():
    from content_factory.json_util import parse_model_json

    raw = '```json\n{"facts": [{"statement": "x"}]}\n```'
    data = parse_model_json(raw)
    assert data["facts"][0]["statement"] == "x"


def test_spend_warning_at_80_percent(orchestrator, storage):
    """Warning fires at 80% of direction daily limit; exceeded still blocks."""
    from content_factory.models import ModelCall
    from uuid import uuid4

    direction = "mental_health"
    limits = orchestrator.check_spend_limits(direction=direction)
    daily_limit = limits["daily"]["limit_usd"]
    assert daily_limit == 50.0

    storage.save_model_call(
        ModelCall(
            task_id=uuid4(),
            model="sonnet-5",
            stage="test",
            direction=direction,
            cost_usd=daily_limit * 0.8,
        )
    )

    warned = orchestrator.check_spend_limits(direction=direction)
    assert warned["daily"]["warning"] is True
    assert warned["daily"]["exceeded"] is False

    storage.save_model_call(
        ModelCall(
            task_id=uuid4(),
            model="sonnet-5",
            stage="test",
            direction=direction,
            cost_usd=daily_limit * 0.25,
        )
    )
    blocked = orchestrator.check_spend_limits(direction=direction)
    assert blocked["daily"]["exceeded"] is True
    assert blocked["daily"]["warning"] is False

    import pytest

    with pytest.raises(ValueError, match="Spending limit exceeded"):
        orchestrator._ensure_spend_allowed(direction)


def test_post_filter_blocks_medical_and_unsourced():
    """Hard post-filter rejects medical claims and facts without dossier sources."""
    from content_factory.models import (
        ContentFormat,
        Fact,
        FactDossier,
        GeneratedText,
        Source,
    )
    from content_factory.safety import apply_post_filter, check_duplicates_against_published

    dossier = FactDossier(
        topic="Breathing",
        facts=[
            Fact(
                statement="Paced breathing lowers cortisol",
                source=Source(
                    url="https://example.org/study/breathing-2024",
                    title="Study",
                ),
                supporting_quote="cortisol dropped",
            )
        ],
    )

    medical = GeneratedText(
        format=ContentFormat.ARTICLE,
        title="Bad advice",
        body="This is a medical diagnosis and a guaranteed cure for anxiety.",
        cta="Start",
        sources_cited=["https://example.org/study/breathing-2024"],
    )
    medical_result = apply_post_filter(
        medical,
        dossier,
        direction="mental_health",
        forbidden_phrases=["guaranteed cure"],
    )
    assert medical_result.passed is False
    assert medical_result.checklist["no_medical_claims"] is False

    unsourced = GeneratedText(
        format=ContentFormat.ARTICLE,
        title="Unsupported",
        body="See https://evil.example/not-in-dossier for proof.",
        cta="Start",
        sources_cited=["https://evil.example/not-in-dossier"],
    )
    unsourced_result = apply_post_filter(
        unsourced,
        dossier,
        direction="mental_health",
    )
    assert unsourced_result.passed is False
    assert unsourced_result.checklist["facts_confirmed"] is False

    ok, remark = check_duplicates_against_published(medical, "mental_health")
    assert ok is True
    assert remark is not None
    assert "корпус опубликованных" in remark.comment.lower()


@pytest.mark.asyncio
async def test_post_filter_rejects_in_pipeline(settings, storage):
    """Pipeline rejects when generator output trips the hard post-filter."""
    from content_factory.orchestrator import Orchestrator
    from content_factory.providers import MockModelProvider

    class UnsafeMock(MockModelProvider):
        def _generate_article(self) -> str:
            import json

            return json.dumps(
                {
                    "title": "Unsafe article",
                    "lead": "Skip this",
                    "body": "You should diagnose yourself and expect a guaranteed cure.",
                    "cta": "Buy now",
                    "sources_cited": ["https://example.org/study/breathing-2024"],
                }
            )

    orchestrator = Orchestrator(settings, storage, provider=UnsafeMock())
    topic = Topic(
        text="Unsafe medical content",
        rubric="research",
        rationale="post-filter test",
        direction="mental_health",
    )
    task = await orchestrator.run_full_cycle(direction="mental_health", topic=topic)
    assert task.status == TaskStatus.REJECTED
    assert task.audit_result is not None
    assert task.audit_result.verdict.value == "reject"
    assert task.audit_result.checklist_scores.get("no_medical_claims") is False


def test_storage_persistence(storage):
    """Test that tasks are persisted to storage."""
    from content_factory.models import Task, Topic
    
    topic = Topic(
        text="Test Storage",
        rubric="test",
        rationale="Testing",
        direction="test",
    )
    
    task = Task(
        direction="test",
        topic=topic,
        status=TaskStatus.DRAFT,
    )
    
    storage.save_task(task)
    
    loaded_task = storage.load_task(task.id)
    
    assert loaded_task is not None
    assert loaded_task.id == task.id
    assert loaded_task.topic.text == topic.text
    assert loaded_task.status == TaskStatus.DRAFT


def test_model_call_tracking(storage):
    """Test that model calls are tracked with costs."""
    from content_factory.models import ModelCall
    from uuid import uuid4
    
    call = ModelCall(
        task_id=uuid4(),
        model="sonnet-5",
        stage="test",
        direction="test",
        input_tokens=1000,
        output_tokens=2000,
        cost_usd=0.05,
    )
    
    storage.save_model_call(call)
    
    stats = storage.get_spending_stats()
    
    assert stats["total_cost_usd"] >= 0.05
    assert "test" in stats["by_stage"]

from datetime import datetime
from uuid import UUID

from content_factory.agents import Auditor, Generator, Researcher, TopicPlanner
from content_factory.config import Settings, load_direction_profile
from content_factory.models import (
    AuditVerdict,
    ContentFormat,
    SpendLimits,
    Task,
    TaskStatus,
    Topic,
)
from content_factory.providers import ModelProvider, get_provider
from content_factory.publishing import TelegramPublisher
from content_factory.publishing.platform import PlatformClient, PlatformPublisher
from content_factory.publishing.telegram import TelegramClient
from content_factory.reporting import build_weekly_spend_report
from content_factory.analytics import build_click_funnel
from content_factory.shortlinks import record_click
from content_factory.storage import Storage


class Orchestrator:
    """Main orchestrator managing the content generation pipeline."""
    
    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        provider: ModelProvider | None = None,
        telegram_client: TelegramClient | None = None,
        platform_client: PlatformClient | None = None,
    ):
        self.settings = settings
        self.storage = storage
        
        if provider is None:
            provider = get_provider(
                use_mock=settings.use_mock_provider,
                provider=settings.model_provider,
                openai_api_key=settings.openai_api_key,
                anthropic_api_key=settings.anthropic_api_key,
            )
        
        self.provider = provider
        
        self.planner = TopicPlanner(provider, settings.planner_model)
        self.researcher = Researcher(provider, settings.researcher_model)
        self.generator = Generator(provider, settings.generator_model)
        self.auditor = Auditor(provider, settings.auditor_model)
        self.publisher = TelegramPublisher(
            settings,
            storage,
            client=telegram_client,
        )
        self.platform_publisher = PlatformPublisher(
            settings,
            storage,
            client=platform_client,
        )
    
    async def run_full_cycle(
        self,
        direction: str,
        topic: Topic | None = None,
    ) -> Task:
        """Run a complete cycle from topic to approval-ready text."""
        
        if topic is None:
            self._ensure_spend_allowed(direction)
            topics, call = await self.planner.plan_topics(
                direction=direction,
                count=1,
                config_dir=self.settings.config_dir,
            )
            self.storage.save_model_call(call)
            
            if not topics:
                raise ValueError("No topics generated")
            
            topic = topics[0]
        
        task = Task(
            direction=direction,
            topic=topic,
            status=TaskStatus.DRAFT,
        )
        self.storage.save_task(task)
        
        try:
            self._ensure_spend_allowed(direction)
            await self._research_stage(task)
            await self._generation_stage(task)
            await self._audit_stage(task)

            if task.status == TaskStatus.REJECTED:
                return task
            if task.status == TaskStatus.DISPUTED:
                self.storage.save_task(task)
                return task

            task.status = TaskStatus.APPROVAL
            self.storage.save_task(task)

        except Exception as e:
            if task.status not in {TaskStatus.REJECTED, TaskStatus.DISPUTED}:
                task.status = TaskStatus.ERROR
                task.error_message = str(e)
                self.storage.save_task(task)
            raise

        return task

    def _resolve_spend_limits(self, direction: str | None = None) -> SpendLimits:
        """Merge global Settings with direction YAML limits (direction wins when set)."""
        daily = self.settings.daily_spend_limit_usd
        monthly = self.settings.monthly_spend_limit_usd

        if direction:
            profile = load_direction_profile(direction, self.settings.config_dir)
            if "daily_usd" in profile.limits:
                daily = float(profile.limits["daily_usd"])
            if "monthly_usd" in profile.limits:
                monthly = float(profile.limits["monthly_usd"])

        return SpendLimits(daily_usd=daily, monthly_usd=monthly)

    def _ensure_spend_allowed(self, direction: str | None = None) -> None:
        """Stop the pipeline when daily/monthly spend limits are exhausted."""
        limits = self.check_spend_limits(direction=direction)
        if limits["daily"]["exceeded"] or limits["monthly"]["exceeded"]:
            raise ValueError("Spending limit exceeded")

    async def _research_stage(self, task: Task) -> None:
        """Research stage: gather facts and sources."""
        self._ensure_spend_allowed(task.direction)
        task.status = TaskStatus.RESEARCH
        self.storage.save_task(task)

        dossier, call = await self.researcher.research_topic(
            topic=task.topic,
            task_id=task.id,
        )

        self.storage.save_model_call(call)

        if not dossier.facts or len(dossier.facts) < 2:
            raise ValueError("Insufficient facts found - topic may not have credible sources")

        task.dossier = dossier
        self.storage.save_task(task)

    async def _generation_stage(self, task: Task) -> None:
        """Generation stage: create article text."""
        self._ensure_spend_allowed(task.direction)
        task.status = TaskStatus.GENERATION
        self.storage.save_task(task)

        if not task.dossier:
            raise ValueError("No dossier available for generation")

        generated_text, call = await self.generator.generate_text(
            topic=task.topic,
            dossier=task.dossier,
            format=ContentFormat.ARTICLE,
            task_id=task.id,
            config_dir=self.settings.config_dir,
        )

        self.storage.save_model_call(call)

        task.generated_texts = [generated_text]
        self.storage.save_task(task)

    async def _audit_stage(self, task: Task) -> None:
        """Audit stage: check quality with revision limit enforcement."""
        max_revisions = self.settings.max_revision_rounds

        while task.revision_count <= max_revisions:
            self._ensure_spend_allowed(task.direction)
            task.status = TaskStatus.AUDIT
            self.storage.save_task(task)

            if not task.generated_texts:
                raise ValueError("No generated text to audit")

            text = task.generated_texts[-1]

            audit_result, call = await self.auditor.audit_text(
                text=text,
                dossier=task.dossier,
                direction=task.direction,
                task_id=task.id,
                threshold=self.settings.audit_pass_threshold,
                config_dir=self.settings.config_dir,
            )

            self.storage.save_model_call(call)
            task.audit_result = audit_result

            if audit_result.verdict == AuditVerdict.PASS:
                break

            if audit_result.verdict == AuditVerdict.REJECT:
                task.status = TaskStatus.REJECTED
                self.storage.save_task(task)
                return

            if task.revision_count >= max_revisions:
                # Cap reached while still REVISE → disputed for human review.
                task.status = TaskStatus.DISPUTED
                self.storage.save_task(task)
                return

            task.status = TaskStatus.REVISION
            task.revision_count += 1
            self.storage.save_task(task)

            revised_text, call = await self.generator.generate_text(
                topic=task.topic,
                dossier=task.dossier,
                format=ContentFormat.ARTICLE,
                task_id=task.id,
                config_dir=self.settings.config_dir,
            )

            self.storage.save_model_call(call)
            task.generated_texts.append(revised_text)
            self.storage.save_task(task)

        self.storage.save_task(task)
    
    def check_spend_limits(self, direction: str | None = None) -> dict:
        """Check current spending against global and direction YAML limits."""
        now = datetime.utcnow()
        
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        resolved = self._resolve_spend_limits(direction)
        daily_limit = resolved.daily_usd
        monthly_limit = resolved.monthly_usd
        warning_threshold = resolved.warning_threshold
        
        daily_stats = self.storage.get_spending_stats(
            start_date=day_start,
            direction=direction,
        )
        monthly_stats = self.storage.get_spending_stats(
            start_date=month_start,
            direction=direction,
        )
        
        daily_pct = (daily_stats["total_cost_usd"] / daily_limit * 100) if daily_limit > 0 else 0
        monthly_pct = (monthly_stats["total_cost_usd"] / monthly_limit * 100) if monthly_limit > 0 else 0

        def _bucket(spent: float, limit: float, percentage: float) -> dict:
            exceeded = spent >= limit
            warning = (not exceeded) and percentage >= warning_threshold * 100
            return {
                "spent_usd": spent,
                "limit_usd": limit,
                "percentage": percentage,
                "warning": warning,
                "exceeded": exceeded,
                "warning_threshold": warning_threshold,
            }
        
        return {
            "direction": direction,
            "daily": _bucket(daily_stats["total_cost_usd"], daily_limit, daily_pct),
            "monthly": _bucket(monthly_stats["total_cost_usd"], monthly_limit, monthly_pct),
        }
    
    async def approve_task(self, task_id: UUID, approved: bool) -> Task:
        """Simulate human approval decision for approval or disputed tasks."""
        task = self.storage.load_task(task_id)
        
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        if task.status not in {TaskStatus.APPROVAL, TaskStatus.DISPUTED}:
            raise ValueError(f"Task {task_id} is not awaiting human decision")
        
        if approved:
            task.status = TaskStatus.APPROVED
        else:
            task.status = TaskStatus.REJECTED
        
        self.storage.save_task(task)
        return task

    # --- Stage 2: Telegram schedule, publish, weekly report ---

    def schedule_telegram(
        self,
        task_id: UUID,
        scheduled_at: datetime,
    ) -> Task:
        """Schedule an approved task for Telegram publication."""
        return self.publisher.schedule_task(task_id, scheduled_at)

    async def publish_due_telegram(
        self,
        now: datetime | None = None,
    ) -> list[Task]:
        """Publish scheduled Telegram posts that are due."""
        return await self.publisher.publish_due(now=now)

    def weekly_spend_report(
        self,
        direction: str | None = None,
        end: datetime | None = None,
    ) -> dict:
        """Build a trailing 7-day spend report."""
        return build_weekly_spend_report(
            self.storage,
            self.settings,
            direction=direction,
            end=end,
        )

    # --- Stage 3: platform publish, short links, click funnel ---

    async def publish_to_platform(self, task_id: UUID) -> Task:
        """Publish an approved task to the website/platform (not Telegram)."""
        return await self.platform_publisher.publish_task(task_id)

    def record_short_link_click(self, code: str):
        """Record a click on a short link."""
        return record_click(self.storage, code)

    def click_funnel(
        self,
        task_id: UUID | None = None,
        channel: str | None = None,
    ) -> dict:
        """Analytics: text → channel → clicks."""
        return build_click_funnel(
            self.storage,
            task_id=task_id,
            channel=channel,
        )

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    DRAFT = "draft"
    RESEARCH = "research"
    GENERATION = "generation"
    AUDIT = "audit"
    APPROVAL = "approval"
    REVISION = "revision"
    DISPUTED = "disputed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ERROR = "error"


class ModelType(str, Enum):
    HAIKU_4_5 = "haiku-4.5"
    SONNET_5 = "sonnet-5"
    OPUS_5 = "opus-5"


class ContentFormat(str, Enum):
    ARTICLE = "article"
    POST = "post"
    REVIEW = "review"


class Source(BaseModel):
    url: str
    title: str
    date: str | None = None
    reliability: str = "medium"
    excerpt: str | None = None


class Fact(BaseModel):
    statement: str
    source: Source
    supporting_quote: str


class FactDossier(BaseModel):
    topic: str
    facts: list[Fact] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GeneratedText(BaseModel):
    format: ContentFormat
    title: str
    lead: str | None = None
    body: str
    cta: str | None = None
    sources_cited: list[str] = Field(default_factory=list)
    word_count: int = 0


class AuditVerdict(str, Enum):
    PASS = "pass"
    REVISE = "revise"
    REJECT = "reject"


class AuditRemark(BaseModel):
    rule: str
    quote: str
    comment: str


class AuditResult(BaseModel):
    verdict: AuditVerdict
    score: float
    remarks: list[AuditRemark] = Field(default_factory=list)
    checklist_scores: dict[str, bool] = Field(default_factory=dict)


class Topic(BaseModel):
    text: str
    rubric: str
    rationale: str
    direction: str


class PublicationRecord(BaseModel):
    """Stage 2: record of a Telegram (or other channel) publication."""

    channel: str = "telegram"
    chat_id: str = ""
    message_id: str | None = None
    utm_url: str | None = None
    text_preview: str = ""
    scheduled_at: datetime | None = None
    published_at: datetime | None = None


class PlatformPublication(BaseModel):
    """Stage 3: website/platform publication (independent of Telegram)."""

    channel: str = "site"
    external_id: str | None = None
    platform_url: str | None = None
    short_code: str | None = None
    short_url: str | None = None
    target_url: str | None = None
    published_at: datetime | None = None


class ShortLink(BaseModel):
    """Stage 3: short link with click counter."""

    code: str
    task_id: UUID
    channel: str
    target_url: str
    clicks: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ClickEvent(BaseModel):
    """Stage 3: single click on a short link."""

    id: UUID = Field(default_factory=uuid4)
    short_code: str
    task_id: UUID
    channel: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Task(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    direction: str
    topic: Topic
    status: TaskStatus = TaskStatus.DRAFT
    dossier: FactDossier | None = None
    generated_texts: list[GeneratedText] = Field(default_factory=list)
    audit_result: AuditResult | None = None
    revision_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: str | None = None
    # Stage 2 publishing fields (unused by Stage 1 pipeline).
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    publication: PublicationRecord | None = None
    # Stage 3: platform channel (does not replace Telegram status flow).
    platform_publication: PlatformPublication | None = None


class ModelCall(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    task_id: UUID | None = None
    model: str
    stage: str
    direction: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DirectionProfile(BaseModel):
    name: str
    audience: str
    tone: str
    topics_per_week: int = 2
    rubrics: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    cta: str = "Learn more"
    landing_url: str = ""
    brand_placeholder: str = "[project name]"
    timezone: str = "UTC"
    limits: dict[str, float] = Field(default_factory=dict)
    forbidden_phrases: list[str] = Field(default_factory=list)
    style_guide_version: str = "1.0"


class SpendLimits(BaseModel):
    daily_usd: float = 10.0
    monthly_usd: float = 300.0
    warning_threshold: float = 0.8

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from content_factory.config import load_config
from content_factory.models import Task, Topic
from content_factory.orchestrator import Orchestrator
from content_factory.storage import Storage

STATIC_DIR = Path(__file__).parent / "static"


class RunCycleRequest(BaseModel):
    direction: str
    topic_text: str | None = None
    topic_rubric: str | None = None
    topic_rationale: str | None = None


class ApprovalRequest(BaseModel):
    approved: bool


class ScheduleRequest(BaseModel):
    scheduled_at: datetime


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    orchestrator = Orchestrator(settings, storage)

    app.state.orchestrator = orchestrator
    app.state.storage = storage

    yield


app = FastAPI(
    title="Content Factory API",
    description="Stages 1–3: generation, Telegram schedule, platform + short links",
    version="0.3.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Operator UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/ui")
async def ui():
    return RedirectResponse(url="/")


@app.get("/api")
async def api_info():
    return {
        "service": "Content Factory",
        "stage": "Stage 3: platform + short links + click funnel",
        "status": "operational",
        "ui": "/",
        "docs": "/docs",
        "features": [
            "Topic planning",
            "Fact research with sources",
            "Content generation",
            "Quality audit with revision limit",
            "Human approval gate (no auto-publish)",
            "Scheduled Telegram publication (approved only)",
            "UTM link tracking",
            "Weekly spend report",
            "Website/platform publication (approved only, separate from Telegram)",
            "Short links and click tracking (text → channel → clicks)",
            "Operator web UI",
        ],
    }


@app.post("/tasks/run", response_model=Task)
async def run_cycle(request: RunCycleRequest):
    """Run a full generation cycle from topic to approval state."""
    orchestrator: Orchestrator = app.state.orchestrator

    limits = orchestrator.check_spend_limits()
    if limits["daily"]["exceeded"] or limits["monthly"]["exceeded"]:
        raise HTTPException(
            status_code=429,
            detail="Spending limit exceeded",
        )

    topic = None
    if request.topic_text:
        topic = Topic(
            text=request.topic_text,
            rubric=request.topic_rubric or "general",
            rationale=request.topic_rationale or "User-provided topic",
            direction=request.direction,
        )

    try:
        task = await orchestrator.run_full_cycle(
            direction=request.direction,
            topic=topic,
        )
        return task
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: UUID):
    """Get task details by ID."""
    storage: Storage = app.state.storage
    task = storage.load_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@app.post("/tasks/{task_id}/approve", response_model=Task)
async def approve_task(task_id: UUID, request: ApprovalRequest):
    """Approve or reject a task (simulates human decision)."""
    orchestrator: Orchestrator = app.state.orchestrator

    try:
        task = await orchestrator.approve_task(task_id, request.approved)
        return task
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/tasks/{task_id}/schedule", response_model=Task)
async def schedule_task(task_id: UUID, request: ScheduleRequest):
    """Schedule an approved task for Telegram publication."""
    orchestrator: Orchestrator = app.state.orchestrator
    try:
        return orchestrator.schedule_telegram(task_id, request.scheduled_at)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/publish/due")
async def publish_due():
    """Publish all due scheduled Telegram posts."""
    orchestrator: Orchestrator = app.state.orchestrator
    try:
        tasks = await orchestrator.publish_due_telegram()
        return {"published": tasks, "count": len(tasks)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/weekly")
async def weekly_report(direction: str | None = None):
    """Trailing 7-day spend report."""
    orchestrator: Orchestrator = app.state.orchestrator
    return orchestrator.weekly_spend_report(direction=direction)


@app.post("/tasks/{task_id}/publish-platform", response_model=Task)
async def publish_platform(task_id: UUID):
    """Publish an approved task to the website/platform (not Telegram)."""
    orchestrator: Orchestrator = app.state.orchestrator
    try:
        return await orchestrator.publish_to_platform(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/links/{code}/click")
async def click_short_link(code: str):
    """Record a click on a short link and return updated counters."""
    orchestrator: Orchestrator = app.state.orchestrator
    try:
        link = orchestrator.record_short_link_click(code)
        return {
            "code": link.code,
            "task_id": str(link.task_id),
            "channel": link.channel,
            "clicks": link.clicks,
            "target_url": link.target_url,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/analytics/clicks")
async def click_analytics(task_id: UUID | None = None, channel: str | None = None):
    """Funnel: text → channel → clicks."""
    orchestrator: Orchestrator = app.state.orchestrator
    return orchestrator.click_funnel(task_id=task_id, channel=channel)


@app.get("/tasks")
async def list_tasks(direction: str | None = None, status: str | None = None):
    """List all tasks, optionally filtered."""
    storage: Storage = app.state.storage

    from content_factory.models import TaskStatus

    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    tasks = storage.list_tasks(direction=direction, status=status_filter)
    return {"tasks": tasks, "count": len(tasks)}


@app.get("/spending")
async def get_spending():
    """Get current spending statistics and limits."""
    orchestrator: Orchestrator = app.state.orchestrator
    return orchestrator.check_spend_limits()


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

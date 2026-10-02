import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from content_factory.models import ClickEvent, ModelCall, ShortLink, Task, TaskStatus


class Storage:
    """Simple JSON-based storage for tasks, model calls, and Stage 3 short links."""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.tasks_dir = self.data_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        self.calls_dir = self.data_dir / "calls"
        self.calls_dir.mkdir(parents=True, exist_ok=True)

        self.short_links_dir = self.data_dir / "short_links"
        self.short_links_dir.mkdir(parents=True, exist_ok=True)

        self.clicks_dir = self.data_dir / "clicks"
        self.clicks_dir.mkdir(parents=True, exist_ok=True)
    
    def save_task(self, task: Task) -> None:
        task.updated_at = datetime.utcnow()
        task_file = self.tasks_dir / f"{task.id}.json"
        
        with open(task_file, "w") as f:
            json.dump(task.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    
    def load_task(self, task_id: UUID) -> Task | None:
        task_file = self.tasks_dir / f"{task_id}.json"
        
        if not task_file.exists():
            return None
        
        with open(task_file) as f:
            data = json.load(f)
        
        return Task(**data)
    
    def list_tasks(
        self,
        direction: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[Task]:
        tasks = []
        
        for task_file in self.tasks_dir.glob("*.json"):
            with open(task_file) as f:
                data = json.load(f)
            
            task = Task(**data)
            
            if direction and task.direction != direction:
                continue
            
            if status and task.status != status:
                continue
            
            tasks.append(task)
        
        return sorted(tasks, key=lambda t: t.created_at)
    
    def save_model_call(self, call: ModelCall) -> None:
        call_file = self.calls_dir / f"{call.id}.json"
        
        with open(call_file, "w") as f:
            json.dump(call.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    
    def get_spending_stats(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        total_cost = 0.0
        calls_by_stage = {}
        calls_by_model = {}
        
        for call_file in self.calls_dir.glob("*.json"):
            with open(call_file) as f:
                data = json.load(f)
            
            call = ModelCall(**data)
            
            if direction and call.direction != direction:
                continue
            if start_date and call.timestamp < start_date:
                continue
            if end_date and call.timestamp > end_date:
                continue
            
            total_cost += call.cost_usd
            
            calls_by_stage[call.stage] = calls_by_stage.get(call.stage, 0) + call.cost_usd
            calls_by_model[call.model] = calls_by_model.get(call.model, 0) + call.cost_usd
        
        return {
            "total_cost_usd": total_cost,
            "by_stage": calls_by_stage,
            "by_model": calls_by_model,
        }

    def save_short_link(self, link: ShortLink) -> None:
        path = self.short_links_dir / f"{link.code}.json"
        with open(path, "w") as f:
            json.dump(link.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

    def load_short_link(self, code: str) -> ShortLink | None:
        path = self.short_links_dir / f"{code}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return ShortLink(**json.load(f))

    def list_short_links(
        self,
        task_id: UUID | None = None,
        channel: str | None = None,
    ) -> list[ShortLink]:
        links: list[ShortLink] = []
        for path in self.short_links_dir.glob("*.json"):
            with open(path) as f:
                link = ShortLink(**json.load(f))
            if task_id and link.task_id != task_id:
                continue
            if channel and link.channel != channel:
                continue
            links.append(link)
        return sorted(links, key=lambda item: item.created_at)

    def save_click_event(self, *, code: str, task_id: UUID, channel: str) -> ClickEvent:
        event = ClickEvent(short_code=code, task_id=task_id, channel=channel)
        path = self.clicks_dir / f"{event.id}.json"
        with open(path, "w") as f:
            json.dump(event.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
        return event
    
    def get_task_history(self, task_id: UUID) -> list[dict[str, Any]]:
        """Get all events for a task (simplified version)."""
        task = self.load_task(task_id)
        
        if not task:
            return []
        
        history = [
            {
                "timestamp": task.created_at.isoformat(),
                "event": "task_created",
                "status": task.status.value,
            },
            {
                "timestamp": task.updated_at.isoformat(),
                "event": "task_updated",
                "status": task.status.value,
            },
        ]
        
        return history

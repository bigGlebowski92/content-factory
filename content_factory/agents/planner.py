import json
from typing import Any

from content_factory.config import load_direction_profile
from content_factory.json_util import parse_model_json
from content_factory.models import ModelCall, ModelType, Topic
from content_factory.providers import ModelProvider


class TopicPlanner:
    """Agent responsible for planning weekly topics."""
    
    def __init__(self, provider: ModelProvider, model: ModelType = ModelType.HAIKU_4_5):
        self.provider = provider
        self.model = model
    
    async def plan_topics(
        self,
        direction: str,
        count: int = 2,
        config_dir: str = "config",
    ) -> tuple[list[Topic], ModelCall]:
        profile = load_direction_profile(direction, config_dir)
        
        prompt = f"""Ты — контент-планировщик wellness-платформы.

ВАЖНО: topic и rationale пиши на русском языке.

Направление: {profile.name}
Аудитория: {profile.audience}
Тон: {profile.tone}
Рубрики: {', '.join(profile.rubrics) if profile.rubrics else 'research, practical_guide, q_and_a'}

Сгенерируй {count} тем на эту неделю. Каждая тема должна:
- соответствовать одной из рубрик
- быть релевантной аудитории
- давать читателю понятную пользу
- включать краткое обоснование (rationale)

Ответь JSON:
{{
    "topics": [
        {{
            "topic": "Полный заголовок темы на русском",
            "rubric": "rubric_name",
            "rationale": "Почему эта тема сейчас — на русском"
        }}
    ]
}}"""

        response = await self.provider.generate(
            prompt=prompt,
            model=self.model,
            max_tokens=2048,
        )
        
        try:
            data = parse_model_json(response["content"])
            topics = [
                Topic(
                    text=t["topic"],
                    rubric=t["rubric"],
                    rationale=t["rationale"],
                    direction=direction,
                )
                for t in data.get("topics", [])[:count]
            ]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            topics = []
        
        usage = response["usage"]
        model_call = ModelCall(
            task_id=None,
            model=self.model.value,
            stage="planner",
            direction=direction,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cached_tokens=usage.get("cache_read_tokens", 0),
            cost_usd=self._calculate_cost(usage),
        )
        
        return topics, model_call
    
    def _calculate_cost(self, usage: dict[str, int]) -> float:
        pricing = {
            "haiku-4.5": {"input": 1.0, "output": 5.0, "cache": 0.1},
            "sonnet-5": {"input": 2.0, "output": 10.0, "cache": 0.2},
            "opus-5": {"input": 5.0, "output": 25.0, "cache": 0.5},
        }
        
        model_pricing = pricing.get(self.model.value, pricing["haiku-4.5"])
        
        input_cost = usage["input_tokens"] * model_pricing["input"] / 1_000_000
        output_cost = usage["output_tokens"] * model_pricing["output"] / 1_000_000
        cache_cost = usage.get("cache_read_tokens", 0) * model_pricing["cache"] / 1_000_000
        
        return input_cost + output_cost + cache_cost

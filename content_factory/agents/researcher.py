import json

from content_factory.json_util import parse_model_json
from content_factory.models import Fact, FactDossier, ModelCall, ModelType, Source, Topic
from content_factory.providers import ModelProvider


class Researcher:
    """Agent responsible for gathering facts and sources."""
    
    def __init__(self, provider: ModelProvider, model: ModelType = ModelType.SONNET_5):
        self.provider = provider
        self.model = model
    
    async def research_topic(
        self,
        topic: Topic,
        task_id,
    ) -> tuple[FactDossier, ModelCall]:
        prompt = f"""Ты — исследователь, собираешь факты для создания контента.

ВАЖНО: statement и supporting_quote пиши на русском языке. Названия источников можно оставить как в оригинале.

Тема: {topic.text}
Рубрика: {topic.rubric}

Исследуй тему и собери fact dossier. Найди 3–5 достоверных фактов для авторитетного материала.

Для каждого факта укажи:
- чёткую формулировку (statement) на русском
- достоверный источник (URL, title, date)
- supporting_quote на русском (или близкий перевод цитаты)
- reliability: high/medium/low

Ограничения:
- НИКАКИХ медицинских диагнозов и индивидуальных рекомендаций по лечению
- НИКАКИХ медицинских обещаний и гарантий результата
- Только evidence-based информация из надёжных источников
- Предпочтительны научные исследования, официальные организации и peer-reviewed публикации

Ответь JSON:
{{
    "facts": [
        {{
            "statement": "Фактическое утверждение на русском",
            "source": {{
                "url": "https://example.org/study",
                "title": "Название источника",
                "date": "2024-03",
                "reliability": "high"
            }},
            "supporting_quote": "Цитата/перевод цитаты на русском"
        }}
    ]
}}"""

        response = await self.provider.generate(
            prompt=prompt,
            model=self.model,
            max_tokens=3072,
        )
        
        try:
            data = parse_model_json(response["content"])
            facts = []
            sources = []
            
            for fact_data in data.get("facts", []):
                source = Source(**fact_data["source"])
                sources.append(source)
                
                fact = Fact(
                    statement=fact_data["statement"],
                    source=source,
                    supporting_quote=fact_data["supporting_quote"],
                )
                facts.append(fact)
            
            dossier = FactDossier(
                topic=topic.text,
                facts=facts,
                sources=sources,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            dossier = FactDossier(topic=topic.text, facts=[], sources=[])
        
        usage = response["usage"]
        model_call = ModelCall(
            task_id=task_id,
            model=self.model.value,
            stage="researcher",
            direction=topic.direction,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cached_tokens=usage.get("cache_read_tokens", 0),
            cost_usd=self._calculate_cost(usage),
        )
        
        return dossier, model_call
    
    def _calculate_cost(self, usage: dict[str, int]) -> float:
        pricing = {
            "haiku-4.5": {"input": 1.0, "output": 5.0, "cache": 0.1},
            "sonnet-5": {"input": 2.0, "output": 10.0, "cache": 0.2},
            "opus-5": {"input": 5.0, "output": 25.0, "cache": 0.5},
        }
        
        model_pricing = pricing.get(self.model.value, pricing["sonnet-5"])
        
        input_cost = usage["input_tokens"] * model_pricing["input"] / 1_000_000
        output_cost = usage["output_tokens"] * model_pricing["output"] / 1_000_000
        cache_cost = usage.get("cache_read_tokens", 0) * model_pricing["cache"] / 1_000_000
        
        return input_cost + output_cost + cache_cost

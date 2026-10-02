import json

from content_factory.config import load_direction_profile, load_style_guide
from content_factory.json_util import parse_model_json
from content_factory.models import (
    ContentFormat,
    FactDossier,
    GeneratedText,
    ModelCall,
    ModelType,
    Topic,
)
from content_factory.providers import ModelProvider


class Generator:
    """Agent responsible for generating content."""
    
    def __init__(self, provider: ModelProvider, model: ModelType = ModelType.OPUS_5):
        self.provider = provider
        self.model = model
    
    async def generate_text(
        self,
        topic: Topic,
        dossier: FactDossier,
        format: ContentFormat,
        task_id,
        config_dir: str = "config",
    ) -> tuple[GeneratedText, ModelCall]:
        profile = load_direction_profile(topic.direction, config_dir)
        style_guide = load_style_guide(topic.direction, config_dir)
        
        facts_text = "\n".join([
            f"- {fact.statement} (Source: {fact.source.title}, {fact.source.url})"
            for fact in dossier.facts
        ])
        
        format_specs = {
            ContentFormat.ARTICLE: "4 000–6 000 символов. Обязательно: тезис, факты с цитатами, практический вывод, призыв к действию.",
            ContentFormat.POST: "До 1 000 символов. Одна ясная идея со ссылкой на полный материал.",
            ContentFormat.REVIEW: "3 000–5 000 символов. Обязательно: что произошло, почему важно, источники.",
        }
        
        prompt = f"""Ты — экспертный автор контента для wellness-платформы.

ВАЖНО: весь текст (title, lead, body, cta) пиши ТОЛЬКО на русском языке.

Направление: {profile.name}
Аудитория: {profile.audience}
Тон: {profile.tone}

Тема: {topic.text}
Формат: {format.value}
Требования: {format_specs[format]}

Доступные факты и источники:
{facts_text}

Правила стайлгайда:
{json.dumps(style_guide, indent=2, ensure_ascii=False)}

Напиши оригинальный, живой {format.value} по этой теме. Требования:
1. Используй ТОЛЬКО факты из досье
2. Указывай источники с URL в скобках
3. Соблюдай тон и стайлгайд
4. Включи все обязательные элементы формата
5. Для названия бренда используй плейсхолдер {profile.brand_placeholder}
6. Заверши призывом к действию: "{profile.cta}"

КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ:
- НИКАКИХ медицинских диагнозов и индивидуальных рекомендаций по лечению
- НИКАКИХ медицинских обещаний и гарантий результата
- НИКАКИХ утверждений сверх того, что подтверждают источники
- Избегай фраз: {', '.join(style_guide.get('forbidden_phrases', []))}

Пиши естественно, без типичных AI-штампов:
- шаблонных вступлений
- избыточных вводных оборотов
- злоупотребления пассивом
- однотипных конструкций предложений

Ответь JSON:
{{
    "title": "Цепляющий заголовок на русском",
    "lead": "Лид-абзац на русском",
    "body": "Полный текст на русском с цитированием источников",
    "cta": "Призыв к действию на русском",
    "sources_cited": ["url1", "url2"]
}}"""

        response = await self.provider.generate(
            prompt=prompt,
            model=self.model,
            max_tokens=8192,
        )
        
        try:
            data = parse_model_json(response["content"])
            
            generated_text = GeneratedText(
                format=format,
                title=data.get("title", ""),
                lead=data.get("lead"),
                body=data.get("body", ""),
                cta=data.get("cta", profile.cta),
                sources_cited=data.get("sources_cited", []),
                word_count=len(data.get("body", "").split()),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            generated_text = GeneratedText(
                format=format,
                title=topic.text,
                body="Error generating content",
            )
        
        usage = response["usage"]
        model_call = ModelCall(
            task_id=task_id,
            model=self.model.value,
            stage="generator",
            direction=topic.direction,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cached_tokens=usage.get("cache_read_tokens", 0),
            cost_usd=self._calculate_cost(usage),
        )
        
        return generated_text, model_call
    
    def _calculate_cost(self, usage: dict[str, int]) -> float:
        pricing = {
            "haiku-4.5": {"input": 1.0, "output": 5.0, "cache": 0.1},
            "sonnet-5": {"input": 2.0, "output": 10.0, "cache": 0.2},
            "opus-5": {"input": 5.0, "output": 25.0, "cache": 0.5},
        }
        
        model_pricing = pricing.get(self.model.value, pricing["opus-5"])
        
        input_cost = usage["input_tokens"] * model_pricing["input"] / 1_000_000
        output_cost = usage["output_tokens"] * model_pricing["output"] / 1_000_000
        cache_cost = usage.get("cache_read_tokens", 0) * model_pricing["cache"] / 1_000_000
        
        return input_cost + output_cost + cache_cost

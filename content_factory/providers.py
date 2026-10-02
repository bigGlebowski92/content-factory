import json
import random
from abc import ABC, abstractmethod
from typing import Any

from content_factory.models import ModelType


class ModelProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: ModelType,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> dict[str, Any]:
        pass


class MockModelProvider(ModelProvider):
    """Mock provider for testing without API keys."""

    def __init__(self, force_audit_verdict: str | None = None):
        # When set, auditor always returns this verdict ("pass"/"revise"/"reject").
        self.force_audit_verdict = force_audit_verdict

    async def generate(
        self,
        prompt: str,
        model: ModelType,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> dict[str, Any]:
        prompt_lower = prompt.lower()

        # Match most specific stage cues first. Generator/auditor prompts also
        # mention "facts"/"sources", so those keywords alone must not win.
        if (
            "audit this text" in prompt_lower
            or "quality checklist" in prompt_lower
            or "проведи аудит" in prompt_lower
            or "чеклист качества" in prompt_lower
            or ("verdict" in prompt_lower and "checklist" in prompt_lower)
        ):
            response = self._generate_audit()
        elif (
            "compile a fact dossier" in prompt_lower
            or "research this topic" in prompt_lower
            or "fact dossier" in prompt_lower
            or "собери fact dossier" in prompt_lower
            or ("research specialist" in prompt_lower and "facts" in prompt_lower)
        ):
            response = self._generate_research()
        elif "topic" in prompt_lower and (
            "plan" in prompt_lower
            or "планировщик" in prompt_lower
            or '"topics"' in prompt_lower
        ):
            response = self._generate_topics()
        elif (
            "write an original" in prompt_lower
            or "expert content writer" in prompt_lower
            or "экспертный автор" in prompt_lower
            or "напиши оригинальный" in prompt_lower
            or ('"title"' in prompt_lower and '"body"' in prompt_lower and '"cta"' in prompt_lower)
        ):
            response = self._generate_article()
        else:
            response = "Mock response: Task completed successfully."
        
        input_tokens = len(prompt.split()) * 2
        output_tokens = len(response.split()) * 2
        
        return {
            "content": response,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": 0,
            },
        }
    
    def _generate_topics(self) -> str:
        topics = [
            {
                "topic": "Наука осознанного дыхания: что подтверждают исследования",
                "rubric": "research",
                "rationale": "Растёт интерес к практикам управления стрессом на основе доказательств",
            },
            {
                "topic": "Как режим сна влияет на ясность мышления",
                "rubric": "practical_guide",
                "rationale": "Высокий спрос в поиске, частый запрос аудитории",
            },
        ]
        return json.dumps({"topics": topics}, ensure_ascii=False)
    
    def _generate_research(self) -> str:
        dossier = {
            "facts": [
                {
                    "statement": "Осознанное дыхание активирует парасимпатическую нервную систему",
                    "source": {
                        "url": "https://example.org/study/breathing-2024",
                        "title": "Effects of Controlled Breathing on Stress Response",
                        "date": "2024-03",
                        "reliability": "high",
                    },
                    "supporting_quote": "У участников снизился уровень кортизола после 10 минут ритмичного дыхания",
                },
                {
                    "statement": "Регулярная практика улучшает концентрацию и эмоциональную регуляцию",
                    "source": {
                        "url": "https://example.org/journal/mindfulness",
                        "title": "Mindfulness Practice and Cognitive Function",
                        "date": "2024-01",
                        "reliability": "high",
                    },
                    "supporting_quote": "После 8 недель практики группа показала значимый рост устойчивости внимания",
                },
                {
                    "statement": "Техника дыхания 4-7-8 связана со снижением тревожности",
                    "source": {
                        "url": "https://example.org/clinical-trials/anxiety",
                        "title": "Breathing Patterns and Anxiety Management",
                        "date": "2023-11",
                        "reliability": "high",
                    },
                    "supporting_quote": "Показатели тревожности снизились на 31% при структурированных протоколах дыхания",
                },
            ]
        }
        return json.dumps(dossier, ensure_ascii=False)
    
    def _generate_article(self) -> str:
        article = {
            "title": "Наука осознанного дыхания: что показывают исследования",
            "lead": "Новые данные показывают, как простые дыхательные практики меняют реакцию на стресс и помогают яснее мыслить.",
            "body": """Недавние исследования подтверждают: контролируемое дыхание даёт измеримую пользу для управления стрессом и когнитивных функций.

**Как это работает**

При осознанном дыхании активируется парасимпатическая нервная система — естественный механизм успокоения. Исследование 2024 года показало снижение кортизола уже после 10 минут ритмичного дыхания (источник: Effects of Controlled Breathing on Stress Response, https://example.org/study/breathing-2024).

**Доказательства для фокуса и эмоций**

8-недельная практика внимательности улучшила устойчивость внимания у участников (источник: Mindfulness Practice and Cognitive Function, https://example.org/journal/mindfulness). Регулярность помогает укреплять навыки концентрации и эмоциональной регуляции.

**Практика: техника 4-7-8**

В клинических протоколах техника 4-7-8 связала с снижением тревожности примерно на 31% (источник: Breathing Patterns and Anxiety Management, https://example.org/clinical-trials/anxiety):

- вдох на 4 счёта
- задержка на 7
- выдох на 8

**Что это значит для вас**

Если добавить короткую дыхательную практику в день, можно мягко поддержать стрессоустойчивость и ясность. Начните с 5 минут и наращивайте по комфорту.

Готовы попробовать? Начните с короткой guided-практики сегодня.""",
            "cta": "Попробовать практику",
            "sources_cited": [
                "https://example.org/study/breathing-2024",
                "https://example.org/journal/mindfulness",
                "https://example.org/clinical-trials/anxiety",
            ],
        }
        return json.dumps(article, ensure_ascii=False)    
    def _generate_audit(self) -> str:
        if self.force_audit_verdict == "revise":
            score = 0.55
            verdict = "revise"
        elif self.force_audit_verdict == "reject":
            score = 0.2
            verdict = "reject"
        elif self.force_audit_verdict == "pass":
            score = 0.9
            verdict = "pass"
        else:
            score = random.uniform(0.75, 0.95)
            verdict = "pass" if score >= 0.7 else "revise"

        audit = {
            "verdict": verdict,
            "score": score,
            "checklist": {
                "topic_matches_direction": True,
                "facts_confirmed": True,
                "no_medical_claims": True,
                "has_structure": True,
                "style_matches": verdict != "reject",
                "no_duplicates": True,
                "within_length": True,
                "has_cta": True,
                "brand_from_config": True,
                "no_ai_patterns": True,
            },
            "remarks": [],
        }

        if verdict != "pass":
            audit["remarks"].append({
                "rule": "natural_language",
                "quote": "incorporating mindful breathing into your daily routine",
                "comment": "Slightly formal phrasing. Consider: 'adding mindful breathing to your day'",
            })

        return json.dumps(audit, ensure_ascii=False)


class OpenAIModelProvider(ModelProvider):
    """Real OpenAI API provider (default for non-mock runs)."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAI API key is required")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("openai package is required for OpenAIModelProvider") from exc

        self.client = OpenAI(api_key=api_key)
        # Role slots from config map onto current OpenAI chat models.
        self.model_map = {
            ModelType.HAIKU_4_5: "gpt-4o-mini",
            ModelType.SONNET_5: "gpt-4o",
            ModelType.OPUS_5: "gpt-4o",
        }

    async def generate(
        self,
        prompt: str,
        model: ModelType,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> dict[str, Any]:
        model_id = self.model_map.get(model, self.model_map[ModelType.SONNET_5])
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=max_tokens,
        )

        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message else ""
        usage = response.usage

        return {
            "content": content or "",
            "usage": {
                "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "cache_read_tokens": 0,
            },
        }


class AnthropicModelProvider(ModelProvider):
    """Real Anthropic API provider (optional)."""
    
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Anthropic API key is required")
        
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError("anthropic package is required for AnthropicModelProvider")
        
        self.client = Anthropic(api_key=api_key)
        self.model_map = {
            ModelType.HAIKU_4_5: "claude-3-5-haiku-20241022",
            ModelType.SONNET_5: "claude-3-5-sonnet-20241022",
            ModelType.OPUS_5: "claude-opus-4-20250514",
        }
    
    async def generate(
        self,
        prompt: str,
        model: ModelType,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> dict[str, Any]:
        model_id = self.model_map.get(model, self.model_map[ModelType.SONNET_5])
        
        messages = [{"role": "user", "content": prompt}]
        
        kwargs = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        
        if system:
            kwargs["system"] = system
        
        response = self.client.messages.create(**kwargs)
        
        content = response.content[0].text if response.content else ""
        
        return {
            "content": content,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_read_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
            },
        }


def get_provider(
    use_mock: bool = True,
    provider: str = "openai",
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    api_key: str = "",
) -> ModelProvider:
    """Return mock or live provider. Default live backend is OpenAI."""
    if use_mock:
        return MockModelProvider()

    backend = (provider or "openai").lower()
    if backend == "openai":
        key = openai_api_key or api_key
        if not key:
            raise ValueError("OPENAI_API_KEY required when USE_MOCK_PROVIDER=false")
        return OpenAIModelProvider(key)

    if backend == "anthropic":
        key = anthropic_api_key or api_key
        if not key:
            raise ValueError("ANTHROPIC_API_KEY required for anthropic provider")
        return AnthropicModelProvider(key)

    raise ValueError(f"Unknown model provider: {provider}")

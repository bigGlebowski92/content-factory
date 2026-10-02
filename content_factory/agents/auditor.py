import json

from content_factory.config import load_direction_profile, load_style_guide
from content_factory.json_util import parse_model_json
from content_factory.models import (
    AuditRemark,
    AuditResult,
    AuditVerdict,
    FactDossier,
    GeneratedText,
    ModelCall,
    ModelType,
)
from content_factory.providers import ModelProvider
from content_factory.safety import apply_post_filter


class Auditor:
    """Agent responsible for auditing generated content."""
    
    def __init__(self, provider: ModelProvider, model: ModelType = ModelType.SONNET_5):
        self.provider = provider
        self.model = model
    
    async def audit_text(
        self,
        text: GeneratedText,
        dossier: FactDossier,
        direction: str,
        task_id,
        threshold: float = 0.7,
        config_dir: str = "config",
    ) -> tuple[AuditResult, ModelCall]:
        style_guide = load_style_guide(direction, config_dir)
        profile = load_direction_profile(direction, config_dir)
        
        facts_text = "\n".join([
            f"- {fact.statement} (Source: {fact.source.url})"
            for fact in dossier.facts
        ])
        
        checklist = """Чеклист качества (True/False):
1. topic_matches_direction — тема соответствует направлению и рубрике
2. facts_confirmed — все факты подтверждены досье, нет неподтверждённых утверждений
3. no_medical_claims — нет диагнозов, обещаний и индивидуальных медрекомендаций
4. has_structure — есть тезис, аргументы и практический вывод
5. style_matches — тон и лексика соответствуют стайлгайду
6. no_duplicates — нет повторов уже опубликованного
7. within_length — длина уместна для формата
8. has_cta — есть призыв к действию и ссылка
9. brand_from_config — бренд только из заданного плейсхолдера
10. no_ai_patterns — нет явных AI-штампов"""
        
        prompt = f"""Ты — строгий редактор контента. Проведи аудит текста.

ВАЖНО: комментарии в remarks.comment пиши на русском. JSON-ключи и verdict оставляй на английском (pass/revise/reject).

ДОСЬЕ ФАКТОВ (ЕДИНСТВЕННЫЙ ИСТОЧНИК ИСТИНЫ):
{facts_text}

СТАЙЛГАЙД:
{json.dumps(style_guide, indent=2, ensure_ascii=False)}

ТЕКСТ НА ПРОВЕРКУ:
Заголовок: {text.title}
{text.lead or ''}

{text.body}

{text.cta or ''}

{checklist}

Оцени каждый пункт True или False.
Общий score от 0.0 до 1.0:
- score >= {threshold}: verdict = "pass"
- score < {threshold}: verdict = "revise"
- серьёзные нарушения (медицина, неподтверждённые факты): verdict = "reject"

Для проблем укажи remarks:
- rule: какое правило нарушено
- quote: точная цитата из текста
- comment: что улучшить (на русском)

Ответь JSON:
{{
    "verdict": "pass" или "revise" или "reject",
    "score": 0.85,
    "checklist": {{
        "topic_matches_direction": true,
        "facts_confirmed": true
    }},
    "remarks": [
        {{
            "rule": "style_matches",
            "quote": "фрагмент текста",
            "comment": "что улучшить"
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
            
            verdict_str = data.get("verdict", "revise")
            verdict = AuditVerdict(verdict_str)
            
            remarks = [
                AuditRemark(
                    rule=r["rule"],
                    quote=r["quote"],
                    comment=r["comment"],
                )
                for r in data.get("remarks", [])
            ]
            
            audit_result = AuditResult(
                verdict=verdict,
                score=data.get("score", 0.5),
                remarks=remarks,
                checklist_scores=data.get("checklist", {}),
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            audit_result = AuditResult(
                verdict=AuditVerdict.REVISE,
                score=0.5,
                remarks=[],
                checklist_scores={},
            )

        forbidden = list(profile.forbidden_phrases) + list(
            style_guide.get("forbidden_phrases") or []
        )
        post = apply_post_filter(
            text,
            dossier,
            direction=direction,
            forbidden_phrases=forbidden,
        )
        audit_result.checklist_scores.update(post.checklist)
        audit_result.remarks.extend(post.remarks)

        if not post.passed:
            audit_result.verdict = AuditVerdict.REJECT
            audit_result.score = min(audit_result.score, 0.0)
        
        usage = response["usage"]
        model_call = ModelCall(
            task_id=task_id,
            model=self.model.value,
            stage="auditor",
            direction=direction,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cached_tokens=usage.get("cache_read_tokens", 0),
            cost_usd=self._calculate_cost(usage),
        )
        
        return audit_result, model_call
    
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

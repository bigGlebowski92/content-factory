import json

from content_factory.config import load_direction_profile, load_style_guide
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
        
        checklist = """Quality Checklist (rate each True/False):
1. topic_matches_direction - Topic fits the direction and rubric
2. facts_confirmed - All facts match the dossier, no unsupported claims
3. no_medical_claims - No medical diagnoses, promises, or individual recommendations
4. has_structure - Includes thesis, arguments, and practical conclusion
5. style_matches - Tone and vocabulary match style guide
6. no_duplicates - No repetition of previously published content
7. within_length - Length is appropriate for format
8. has_cta - Call to action and link are present
9. brand_from_config - Brand name only from provided placeholder
10. no_ai_patterns - No obvious AI writing patterns (generic openings, excessive transitions, etc.)"""
        
        prompt = f"""You are a critical content reviewer. Audit this text thoroughly.

FACT DOSSIER (ONLY SOURCE OF TRUTH):
{facts_text}

STYLE GUIDE:
{json.dumps(style_guide, indent=2)}

TEXT TO REVIEW:
Title: {text.title}
{text.lead or ''}

{text.body}

{text.cta or ''}

{checklist}

Review the text against this checklist. For each item, evaluate True or False.

Calculate an overall score (0.0 to 1.0) based on checklist items.
- If score >= {threshold}: verdict is "pass"
- If score < {threshold}: verdict is "revise"
- If major violations (medical claims, unsupported facts): verdict is "reject"

For any False items or issues, provide specific remarks with:
- rule: which rule was violated
- quote: exact text excerpt
- comment: specific improvement needed

Respond with JSON:
{{
    "verdict": "pass" or "revise" or "reject",
    "score": 0.85,
    "checklist": {{
        "topic_matches_direction": true,
        "facts_confirmed": true,
        ...
    }},
    "remarks": [
        {{
            "rule": "style_matches",
            "quote": "exact excerpt from text",
            "comment": "what needs improvement"
        }}
    ]
}}"""

        response = await self.provider.generate(
            prompt=prompt,
            model=self.model,
            max_tokens=2048,
        )
        
        try:
            data = json.loads(response["content"])
            
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
        except (json.JSONDecodeError, KeyError, ValueError):
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

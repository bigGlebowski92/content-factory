import json

from content_factory.config import load_direction_profile, load_style_guide
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
            ContentFormat.ARTICLE: "4,000-6,000 characters. Must include: thesis, facts with citations, practical conclusion, call to action.",
            ContentFormat.POST: "Up to 1,000 characters. Single clear idea with link to full article.",
            ContentFormat.REVIEW: "3,000-5,000 characters. Must include: what happened, why it matters, sources.",
        }
        
        prompt = f"""You are an expert content writer for a wellness platform.

Direction: {profile.name}
Audience: {profile.audience}
Tone: {profile.tone}

Topic: {topic.text}
Format: {format.value}
Requirements: {format_specs[format]}

Available Facts and Sources:
{facts_text}

Style Guide Rules:
{json.dumps(style_guide, indent=2)}

Write an original, engaging {format.value} on this topic. Requirements:
1. Use ONLY facts from the provided dossier
2. Cite sources with URLs in parentheses
3. Match the tone and style guide
4. Include all required elements for this format
5. Use {profile.brand_placeholder} as placeholder for brand name
6. End with call to action: "{profile.cta}"

CRITICAL RESTRICTIONS:
- NO medical diagnoses or individual treatment recommendations
- NO medical promises or guaranteed outcomes
- NO claims beyond what sources support
- Avoid these phrases: {', '.join(style_guide.get('forbidden_phrases', []))}

Write naturally, avoiding AI-like patterns such as:
- Generic opening statements
- Excessive transition words
- Passive voice overuse
- Repetitive sentence structures

Respond with JSON:
{{
    "title": "Compelling title",
    "lead": "Opening paragraph (if applicable)",
    "body": "Full text content with inline citations",
    "cta": "Call to action text",
    "sources_cited": ["url1", "url2"]
}}"""

        response = await self.provider.generate(
            prompt=prompt,
            model=self.model,
            max_tokens=4096,
        )
        
        try:
            data = json.loads(response["content"])
            
            generated_text = GeneratedText(
                format=format,
                title=data.get("title", ""),
                lead=data.get("lead"),
                body=data.get("body", ""),
                cta=data.get("cta", profile.cta),
                sources_cited=data.get("sources_cited", []),
                word_count=len(data.get("body", "").split()),
            )
        except (json.JSONDecodeError, KeyError):
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

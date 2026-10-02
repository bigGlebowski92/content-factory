import json

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
        prompt = f"""You are a research specialist gathering facts for content creation.

Topic: {topic.text}
Rubric: {topic.rubric}

Research this topic and compile a fact dossier. Find 3-5 credible facts that support creating authoritative content on this topic.

For each fact, provide:
- A clear statement
- A credible source (URL, title, date)
- A supporting quote from the source
- Reliability rating (high/medium/low)

Important restrictions:
- NO medical diagnoses or individual treatment recommendations
- NO medical promises or guaranteed outcomes
- Only evidence-based information from credible sources
- Prefer scientific studies, official organizations, and peer-reviewed publications

Respond with JSON in this format:
{{
    "facts": [
        {{
            "statement": "Clear factual statement",
            "source": {{
                "url": "https://example.org/study",
                "title": "Source title",
                "date": "2024-03",
                "reliability": "high"
            }},
            "supporting_quote": "Direct quote from source"
        }}
    ]
}}"""

        response = await self.provider.generate(
            prompt=prompt,
            model=self.model,
            max_tokens=3072,
        )
        
        try:
            data = json.loads(response["content"])
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
        except (json.JSONDecodeError, KeyError) as e:
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

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
            or ("verdict" in prompt_lower and "checklist" in prompt_lower)
        ):
            response = self._generate_audit()
        elif (
            "compile a fact dossier" in prompt_lower
            or "research this topic" in prompt_lower
            or ("research specialist" in prompt_lower and "facts" in prompt_lower)
        ):
            response = self._generate_research()
        elif "topic" in prompt_lower and ("plan" in prompt_lower or '"topics"' in prompt_lower):
            response = self._generate_topics()
        elif (
            "write an original" in prompt_lower
            or "expert content writer" in prompt_lower
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
                "topic": "The Science Behind Mindful Breathing Techniques",
                "rubric": "research",
                "rationale": "Growing interest in evidence-based stress management practices",
            },
            {
                "topic": "How Sleep Patterns Affect Mental Clarity",
                "rubric": "practical_guide",
                "rationale": "High search volume, addresses common wellness concern",
            },
        ]
        return json.dumps({"topics": topics}, ensure_ascii=False)
    
    def _generate_research(self) -> str:
        dossier = {
            "facts": [
                {
                    "statement": "Mindful breathing activates the parasympathetic nervous system",
                    "source": {
                        "url": "https://example.org/study/breathing-2024",
                        "title": "Effects of Controlled Breathing on Stress Response",
                        "date": "2024-03",
                        "reliability": "high",
                    },
                    "supporting_quote": "Participants showed reduced cortisol levels after 10 minutes of paced breathing",
                },
                {
                    "statement": "Regular practice improves focus and emotional regulation",
                    "source": {
                        "url": "https://example.org/journal/mindfulness",
                        "title": "Mindfulness Practice and Cognitive Function",
                        "date": "2024-01",
                        "reliability": "high",
                    },
                    "supporting_quote": "8-week intervention group demonstrated significant improvements in attention span",
                },
                {
                    "statement": "4-7-8 breathing technique shows measurable anxiety reduction",
                    "source": {
                        "url": "https://example.org/clinical-trials/anxiety",
                        "title": "Breathing Patterns and Anxiety Management",
                        "date": "2023-11",
                        "reliability": "high",
                    },
                    "supporting_quote": "Anxiety scores decreased by 31% using structured breathing protocols",
                },
            ]
        }
        return json.dumps(dossier, ensure_ascii=False)
    
    def _generate_article(self) -> str:
        article = {
            "title": "The Science Behind Mindful Breathing: What Research Shows",
            "lead": "New research reveals how simple breathing exercises can reshape your stress response and improve mental clarity.",
            "body": """Recent scientific studies demonstrate that controlled breathing techniques offer measurable benefits for stress management and cognitive function.

**How It Works**

When you practice mindful breathing, you activate your parasympathetic nervous system—the body's natural calming mechanism. Research published in March 2024 shows that participants experienced reduced cortisol levels after just 10 minutes of paced breathing exercises (source: Effects of Controlled Breathing on Stress Response, example.org/study/breathing-2024).

**The Evidence for Focus and Emotional Balance**

An 8-week study on mindfulness practice revealed significant improvements in attention span among participants who maintained regular breathing exercises (source: Mindfulness Practice and Cognitive Function, example.org/journal/mindfulness). The research suggests that consistent practice helps strengthen neural pathways associated with focus and emotional regulation.

**Practical Application: The 4-7-8 Technique**

Clinical trials examining the 4-7-8 breathing pattern found a 31% decrease in anxiety scores among participants using this structured approach (source: Breathing Patterns and Anxiety Management, example.org/clinical-trials/anxiety). The technique involves:

- Inhaling for 4 counts
- Holding for 7 counts
- Exhaling for 8 counts

**What This Means for You**

The science is clear: incorporating mindful breathing into your daily routine can create tangible improvements in stress management and mental clarity. Start with 5 minutes per day and gradually increase as you become comfortable with the practice.

Ready to experience the benefits? Try a guided breathing practice today.""",
            "cta": "Start your practice",
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


class AnthropicModelProvider(ModelProvider):
    """Real Anthropic API provider."""
    
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


def get_provider(use_mock: bool = True, api_key: str = "") -> ModelProvider:
    if use_mock:
        return MockModelProvider()
    
    if not api_key:
        raise ValueError("API key required for non-mock provider")
    
    return AnthropicModelProvider(api_key)

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from content_factory.models import DirectionProfile, ModelType, SpendLimits


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    anthropic_api_key: str = ""
    use_mock_provider: bool = True
    
    planner_model: ModelType = ModelType.HAIKU_4_5
    researcher_model: ModelType = ModelType.SONNET_5
    generator_model: ModelType = ModelType.OPUS_5
    auditor_model: ModelType = ModelType.SONNET_5
    
    max_revision_rounds: int = 2
    audit_pass_threshold: float = 0.7
    
    daily_spend_limit_usd: float = 10.0
    monthly_spend_limit_usd: float = 300.0
    
    database_path: str = "data/content_factory.db"
    config_dir: str = "config"

    # Stage 2: Telegram publishing
    use_mock_telegram: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = "@content_factory_test"
    default_landing_url: str = "https://example.com"

    # Stage 3: website/platform + short links
    use_mock_platform: bool = True
    platform_api_url: str = ""
    platform_api_key: str = ""
    short_link_base_url: str = "https://go.example.com"


def load_config() -> Settings:
    return Settings()


def load_direction_profile(direction_name: str, config_dir: str = "config") -> DirectionProfile:
    config_path = Path(config_dir) / "directions" / f"{direction_name}.yaml"
    
    if not config_path.exists():
        return DirectionProfile(name=direction_name)
    
    with open(config_path) as f:
        data = yaml.safe_load(f)
    
    return DirectionProfile(**data)


def load_style_guide(direction_name: str, config_dir: str = "config") -> dict[str, Any]:
    style_path = Path(config_dir) / "style_guides" / f"{direction_name}.yaml"
    
    if not style_path.exists():
        return {
            "rules": [],
            "forbidden_phrases": [
                "medical diagnosis",
                "individual treatment recommendation",
                "guaranteed cure",
                "medical promise",
            ],
            "required_elements": {
                "article": ["thesis", "facts", "conclusion", "cta"],
                "post": ["single_idea", "link"],
                "review": ["what_happened", "why_important", "sources"],
            },
        }
    
    with open(style_path) as f:
        return yaml.safe_load(f)


def load_model_pricing() -> dict[str, dict[str, float]]:
    return {
        "opus-5": {"input": 5.0, "output": 25.0, "cache": 0.5},
        "sonnet-5": {"input": 2.0, "output": 10.0, "cache": 0.2},
        "haiku-4.5": {"input": 1.0, "output": 5.0, "cache": 0.1},
    }


settings = load_config()

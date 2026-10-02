import shutil
from pathlib import Path

import pytest

from content_factory.config import Settings
from content_factory.orchestrator import Orchestrator
from content_factory.providers import MockModelProvider
from content_factory.storage import Storage


@pytest.fixture
def test_data_dir(tmp_path):
    """Create a temporary data directory for tests."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()
    yield str(data_dir)
    shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture
def test_config_dir():
    """Use the real config directory for tests."""
    return "config"


@pytest.fixture
def settings(test_data_dir):
    """Create test settings."""
    return Settings(
        use_mock_provider=True,
        anthropic_api_key="",
        max_revision_rounds=2,
        audit_pass_threshold=0.7,
        daily_spend_limit_usd=10.0,
        monthly_spend_limit_usd=300.0,
        database_path=f"{test_data_dir}/test.db",
        config_dir="config",
    )


@pytest.fixture
def storage(test_data_dir):
    """Create test storage."""
    return Storage(data_dir=test_data_dir)


@pytest.fixture
def mock_provider():
    """Create mock provider."""
    return MockModelProvider()


@pytest.fixture
def orchestrator(settings, storage, mock_provider):
    """Create test orchestrator."""
    return Orchestrator(settings, storage, provider=mock_provider)

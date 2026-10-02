# Content Factory

Автоматизова виробництво контенту з fact-check, human approval, Telegram/майданчиком, UTM і кліками. Реалізація етапів 1–3 ТЗ (27 Sep 2026) + операторський web UI.

## Швидкий старт

```bash
# 1. Клонувати / відкрити проєкт
cd content-factory

# 2. Python 3.10+ (у pyproject зазначено 3.12+, на 3.10 теж працює з mock)
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Залежності
pip install -r requirements.txt
pip install -e .            # опційно, для editable install

# 4. Конфіг
cp .env.example .env
# Для mock: USE_MOCK_PROVIDER=true
# Для OpenAI: USE_MOCK_PROVIDER=false, MODEL_PROVIDER=openai, OPENAI_API_KEY=sk-...

# 5. Запуск UI + API
PYTHONPATH=. uvicorn content_factory.api:app --host 127.0.0.1 --port 8000
```

Відкрий у браузері:

| Що | URL |
|---|---|
| **Web UI** (російською) | http://127.0.0.1:8000/ |
| Swagger API | http://127.0.0.1:8000/docs |
| JSON info | http://127.0.0.1:8000/api |

### OpenAI замість Anthropic
За замовчуванням живий бекенд — **OpenAI** (`MODEL_PROVIDER=openai`).

```bash
# у .env
USE_MOCK_PROVIDER=false
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
```

Ролі пайплайна мапляться так: planner → `gpt-4o-mini`, researcher/auditor/generator → `gpt-4o`.
Anthropic лишається опцією: `MODEL_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`.

### Як протестувати в UI
1. **Новий цикл** → генерація зупиниться на `approval`
2. Обери задачу → **Approve**
3. **Schedule Telegram** (mock-бот) або **Publish to platform** (mock-майданчик)
4. Після platform → **Simulate click** → дивись кліки в Metrics

### Тести
```bash
PYTHONPATH=. pytest tests/ -v
# очікуй 26 passed
```

### CLI (альтернатива UI)
```bash
PYTHONPATH=. python -m content_factory.cli run mental_health --use-mock
PYTHONPATH=. python -m content_factory.cli list
PYTHONPATH=. python -m content_factory.cli spending
PYTHONPATH=. python -m content_factory.cli weekly-report --direction mental_health
```

---

## What This Stage Implements

Stage 1 delivers a **runnable generation core** that takes a topic through the complete pipeline and stops at human approval without publishing anything.

### ✅ Implemented Features

**Full Pipeline Components:**
1. **Topic Planner** - Generates weekly topics with rubrics and rationale
2. **Researcher** - Gathers sourced fact dossiers with URLs and citations
3. **Generator** - Writes original articles based on fact dossiers
4. **Auditor** - Checks quality against 10-point checklist with configurable threshold
5. **Orchestrator** - Manages pipeline flow, retries, and spending limits

**Quality Controls:**
- ✅ Maximum 2 revision rounds (FR-QA-03) - enforced before human handoff
- ✅ Human approval gate - nothing publishes without explicit decision
- ✅ Medical restrictions - bans diagnoses, promises, individual recommendations
- ✅ Fact verification - all claims must trace to dossier sources
- ✅ Style guide compliance - configurable per direction
- ✅ Cost tracking - per-call token and USD tracking

**Configuration System:**
- ✅ Model selection (Haiku 4.5, Sonnet 5, Opus 5) per stage via config
- ✅ Spend limits (daily/monthly) checked before each call
- ✅ Direction profiles (audience, tone, rubrics, forbidden phrases)
- ✅ Style guides loaded from YAML files
- ✅ No hardcoded constants - all settings in config files

**Testing & Mock Provider:**
- ✅ Mock model provider for testing without API keys
- ✅ Real Anthropic provider with environment variable key
- ✅ End-to-end tests covering full pipeline
- ✅ Tests verify revision limit and no-publish gate

## What Is NOT In This Stage

Following the specification, these are deliberately **excluded** from Stage 1:

### Stage 2 Features (Implemented)
- ✅ Scheduled Telegram publication (approved → scheduled → published)
- ✅ UTM tracking on landing links
- ✅ Weekly spend report
- ✅ Mock Telegram client (no real bot required)

### Stage 3 Features (Implemented)
- ✅ Website/platform publishing (approved only, separate from Telegram)
- ✅ Short links and click tracking
- ✅ Analytics funnel: text → channel → clicks
- ✅ Mock platform client (no real network)

### Stage 4 Features (Not Implemented)
- ❌ Instagram/TikTok adaptation
- ❌ Second model opinion on audits
- ❌ Google Docs editing interface
- ❌ Advanced security controls

## Installation

### Prerequisites
- Python 3.12+ (3.10+ works for local mock runs)
- (Optional) Anthropic API key for real API calls

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Or using pyproject.toml
pip install -e .

# Copy and configure environment
cp .env.example .env
# Edit .env and set USE_MOCK_PROVIDER=true (default for testing)
```

### Configuration

Direction profiles and style guides live in `config/`:

```
config/
  directions/
    mental_health.yaml
  style_guides/
    mental_health.yaml
```

Add new directions by creating corresponding YAML files.

## Usage

### Web UI

```bash
PYTHONPATH=. uvicorn content_factory.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/** — operator console for run → approve → Telegram / platform → clicks.

API JSON info: `/api` · Swagger: `/docs`

### Command-Line Interface

Run a complete generation cycle:

```bash
# Using mock provider (no API key needed)
python -m content_factory.cli run mental_health --use-mock

# With a specific topic
python -m content_factory.cli run mental_health \
  --topic "How Sleep Affects Mental Clarity" \
  --rubric "research" \
  --use-mock

# List all tasks
python -m content_factory.cli list

# Check spending
python -m content_factory.cli spending
```

### REST API

Start the API server:

```bash
uvicorn content_factory.api:app --host 0.0.0.0 --port 8000
```

Run a cycle via API:

```bash
curl -X POST http://localhost:8000/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "direction": "mental_health",
    "topic_text": "The Science Behind Mindful Breathing"
  }'
```

Get task status:

```bash
curl http://localhost:8000/tasks/{task_id}
```

Approve a task (simulates human decision):

```bash
curl -X POST http://localhost:8000/tasks/{task_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"approved": true}'
```

Check spending:

```bash
curl http://localhost:8000/spending
```

### Python API

```python
import asyncio
from content_factory import Settings, Orchestrator, Storage
from content_factory.models import Topic

async def main():
    settings = Settings(use_mock_provider=True)
    storage = Storage()
    orchestrator = Orchestrator(settings, storage)
    
    # Run full cycle
    topic = Topic(
        text="Mindfulness and Focus",
        rubric="research",
        rationale="Popular topic",
        direction="mental_health",
    )
    
    task = await orchestrator.run_full_cycle(
        direction="mental_health",
        topic=topic,
    )
    
    print(f"Task {task.id} status: {task.status}")
    print(f"Revision count: {task.revision_count}")
    print(f"Generated texts: {len(task.generated_texts)}")
    
    # Task stops at APPROVAL status - requires human decision
    assert task.status == "approval"
    
    # Simulate human approval
    approved_task = await orchestrator.approve_task(task.id, approved=True)
    print(f"Final status: {approved_task.status}")

asyncio.run(main())
```

## Running Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=content_factory --cov-report=html

# Specific test file
pytest tests/test_pipeline.py -v

# Test specific feature
pytest tests/test_pipeline.py::test_revision_limit_enforced -v
```

Key tests verify:
- ✅ Full end-to-end pipeline completes
- ✅ Revision limit (max 2 rounds) is enforced
- ✅ Nothing publishes without approval
- ✅ Fact dossier has sourced citations
- ✅ Generated text has required structure
- ✅ Audit results include checklist
- ✅ Spending limits are tracked

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Orchestrator                        │
│  (manages pipeline, enforces revision limit, tracks $)  │
└─────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
  ┌──────────┐      ┌──────────┐      ┌──────────┐
  │ Planner  │      │Researcher│      │Generator │
  │ (topics) │      │ (facts)  │      │ (texts)  │
  └──────────┘      └──────────┘      └──────────┘
                                             │
                                             ▼
                                      ┌──────────┐
                                      │ Auditor  │
                                      │  (QA)    │
                                      └──────────┘
                                             │
                                             ▼
                                    ┌────────────────┐
                                    │ APPROVAL STATE │
                                    │  (human gate)  │
                                    └────────────────┘
```

**Agent Responsibilities:**

- **Planner** (Haiku 4.5): Generates topic ideas by direction
- **Researcher** (Sonnet 5): Gathers 3-5 credible facts with sources
- **Generator** (Opus 5): Writes original articles from fact dossiers
- **Auditor** (Sonnet 5): Reviews against 10-point quality checklist

**Quality Checklist (10 points):**

1. Topic matches direction and rubric
2. All facts confirmed by dossier
3. No medical claims/diagnoses/promises
4. Has structure (thesis, arguments, conclusion)
5. Style matches guide
6. No duplicates with published content
7. Within length limits
8. Has call-to-action and link
9. Brand name only from config
10. No obvious AI writing patterns

## Using Real Anthropic API

To use real Anthropic models instead of the mock provider:

1. Get an API key from [Anthropic Console](https://console.anthropic.com/)

2. Set environment variables:
   ```bash
   export ANTHROPIC_API_KEY="your-key-here"
   export USE_MOCK_PROVIDER=false
   ```

3. Or update `.env`:
   ```
   USE_MOCK_PROVIDER=false
   ANTHROPIC_API_KEY=your-key-here
   ```

**Never commit API keys.** The `.env` file is gitignored.

### Cost Estimates (with real API)

Based on specification estimates:

- **One article** (economical): ~$0.30-0.42 USD
- **One article** (with revision): ~$0.55-0.75 USD
- **20 topics/month**: ~$10-15 USD (economical scenario)
- **40 topics/month**: ~$20-30 USD (economical scenario)

Mock provider is free and sufficient for development/testing.

## Project Structure

```
content_factory/
├── agents/
│   ├── planner.py       # Topic planning agent
│   ├── researcher.py    # Fact research agent
│   ├── generator.py     # Content generation agent
│   └── auditor.py       # Quality audit agent
├── config/
│   └── __init__.py      # Configuration loading
├── models.py            # Data models (Task, Topic, etc.)
├── providers.py         # Mock & Anthropic providers
├── storage.py           # JSON-based task storage
├── orchestrator.py      # Pipeline orchestration
├── api.py              # FastAPI REST interface
└── cli.py              # Command-line interface

config/
├── directions/          # Direction profiles (YAML)
└── style_guides/        # Style guides (YAML)

tests/
├── conftest.py          # Test fixtures
└── test_pipeline.py     # End-to-end tests
```

## Medical Safety

Per specification requirements, the system **blocks**:

- ❌ Medical diagnoses
- ❌ Individual treatment recommendations
- ❌ Medical promises or guaranteed outcomes

These restrictions are:
1. Baked into generation prompts
2. Checked by the auditor
3. Configurable via `forbidden_phrases` in direction profiles

Example forbidden phrases:
- "guaranteed cure"
- "diagnose yourself"
- "medical diagnosis"
- "individual treatment"

## Revision Limit

The specification requires **maximum 2 revision rounds** (FR-QA-03).

How it works:
1. Generator creates initial text
2. Auditor reviews → PASS, REVISE, or REJECT
3. If REVISE and `revision_count < 2`: regenerate and audit again
4. If REVISE and `revision_count >= 2`: stop, send to human as "disputed"
5. If PASS: proceed to approval
6. If REJECT: stop, mark as rejected

Tests verify this limit is enforced.

## Spending Limits

Per specification (NFR-04):

- Default: $10/day, $300/month
- Checked before each model call
- Configurable per direction and globally
- Warning at 80%, stop at 100%

Check current spending:

```bash
python -m content_factory.cli spending
```

## Data Storage

Stage 1 uses simple JSON file storage:

```
data/
├── tasks/           # One JSON file per task
└── calls/           # One JSON file per model call
```

Each task stores:
- Topic and direction
- Fact dossier with sources
- Generated texts (all versions)
- Audit results
- Revision count
- Status history

## Adding a New Direction

1. Create direction profile:
   ```yaml
   # config/directions/new_direction.yaml
   name: "Direction Name"
   audience: "Target audience description"
   tone: "Desired tone"
   topics_per_week: 2
   rubrics: ["rubric1", "rubric2"]
   forbidden_phrases: ["phrase1", "phrase2"]
   ```

2. Create style guide:
   ```yaml
   # config/style_guides/new_direction.yaml
   version: "1.0"
   rules:
     - "Rule 1"
     - "Rule 2"
   forbidden_phrases: ["phrase1"]
   ```

3. Run pipeline:
   ```bash
   python -m content_factory.cli run new_direction --use-mock
   ```

No code changes required.

## Roadmap: Future Stages

Per the specification, these stages are **documented but not implemented**:

### Stage 2 (Current)
- ✅ Scheduled Telegram publication (approved only)
- ✅ UTM link tracking
- ✅ Weekly spend report
- ✅ Mock Telegram client for tests

### Stage 3 (Current)
- ✅ Website/platform publishing (approved only)
- ✅ Short links + click counters
- ✅ Analytics: text → channel → clicks
- ✅ Mock platform client for tests

### Stage 4 (Not in Current Build)
- Instagram & TikTok formats
- Second model opinion
- Google Docs editing UI
- Cost optimization (<$0.40/article)

## Contributing

This is Stage 1 of a phased implementation. Future work includes:
- Publishing modules (Stages 2-3)
- Analytics integration (Stage 3)
- Additional social channels (Stage 4)
- Enhanced safety controls (Stage 4)

## License

Proprietary - Implementation of customer specification "Контент-завод" dated 27 Sep 2026.

## Support

For questions about this implementation, refer to:
- Technical Specification (27 Sep 2026)
- Stage 1 acceptance criteria (AC-1-01 through AC-1-06)
- Test suite in `tests/test_pipeline.py`

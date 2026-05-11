# HCV API — Claude Code Project Brain

## What This Project Is

A production-grade citation verification API for legal AI platforms.
It extracts legal citations from text, verifies them against legal databases,
checks argument support, and generates cryptographic audit trails.

First client target: HAQQ Legal AI (haqq.ai)
Current phase: MVP (Phase 1 — existence checking with CourtListener)

## Architecture Overview

See @docs/architecture.md for full system design.
See @docs/data_sources.md for database integration status.

## Stack

- Python 3.11 + FastAPI (async)
- PostgreSQL 16 (audit logs)
- Redis (citation caching, 24hr TTL)
- eyecite (citation extraction — open source, Harvard/Free Law Project)
- legal-bert-base-uncased (semantic argument check — Phase 2 only)
- Docker (deployment)

## Python Environment Setup

This project uses a local virtual environment to avoid dependency conflicts.

```bash
# Activate virtual environment (ALWAYS do this first)
source venv/bin/activate

# Verify you're using the project Python
which python
# Should show: /path/to/hcv-api/venv/bin/python
```

## Bash Commands

```bash
# Start development server (with venv activated)
uvicorn api.main:app --reload --port 8001

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_extraction.py -v

# Run tests with coverage
pytest tests/ --cov=api --cov-report=term-missing

# Install dependencies
pip install -r requirements.txt

# Database migrations (using Alembic)
alembic upgrade head
alembic revision --autogenerate -m "description"

# Format code
black api/ tests/
isort api/ tests/

# Type check
mypy api/

# Start all services (Postgres + Redis)
brew services start postgresql@16
brew services start redis
```

## Code Style Rules

- ALWAYS use async/await for any I/O operation (database, HTTP, Redis)
- ALWAYS use Pydantic v2 models for request and response validation
- ALWAYS add type hints to every function signature
- NEVER use `print()` — use `logger = logging.getLogger(__name__)` instead
- NEVER commit secrets or API keys — use environment variables via python-dotenv
- NEVER use `SELECT *` — always name columns explicitly
- Use `httpx.AsyncClient` for all outbound HTTP — never `requests`
- Keep functions under 40 lines — if longer, split into helpers
- Every function that calls an external API must have a try/except with specific error handling

## Project Structure

```
api/
  main.py          — FastAPI app factory, middleware, startup events
  config.py        — Settings via pydantic-settings
  routes/
    verify.py      — POST /v1/verify (main endpoint)
    audit.py       — GET /v1/audit/{id} (retrieve audit records)
    health.py      — GET /health (uptime check)
  services/
    extractor.py   — eyecite wrapper, citation extraction
    verifier.py    — Orchestrates parallel database queries
    sources/
      courtlistener.py  — CourtListener API integration
      lexisnexis.py     — LexisNexis API integration (Phase 2)
    scorer.py      — Confidence score aggregation
    semantic.py    — Argument support check (Phase 2)
    cache.py       — Redis caching layer
    audit.py       — Audit trail generation
  models/
    request.py     — VerifyRequest, AuditRequest Pydantic models
    response.py    — VerifyResponse, CitationResult Pydantic models
  db/
    connection.py  — Async PostgreSQL connection pool (asyncpg)
    queries.py     — All raw SQL queries (no ORM)
  utils/
    hashing.py     — SHA-256 audit hash generation
    rate_limit.py  — Per-API-key rate limiting
tests/
  fixtures/        — Real legal document samples for testing
  test_extraction.py
  test_verification.py
  test_scoring.py
  test_api.py      — Integration tests against live endpoints
docs/
  architecture.md
  data_sources.md
  api_reference.md
```

## Testing Rules

- ALWAYS write a test before or immediately after writing a function
- Test files mirror the source structure: `api/services/extractor.py` → `tests/test_extraction.py`
- Use `pytest-asyncio` for async tests
- Use `httpx.AsyncClient` with `app` for API integration tests — never start a real server
- Every external API call in tests MUST be mocked with `pytest-mock` or `respx`
- Run `pytest tests/ -v` after every feature completion. Fix failures before moving on.

## Git Rules

- NEVER commit directly to main
- Create a branch for each phase: `phase-1-mvp`, `phase-2-lexis`, `phase-3-semantic`
- Commit message format: `type(scope): description`
  - Types: feat, fix, test, docs, refactor, chore
  - Example: `feat(verifier): add CourtListener parallel query`
- NEVER commit .env files
- Run tests before every commit

## Error Handling Standard

Every function that calls an external API must follow this pattern:

```python
async def call_external_api(param: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=...)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        logger.warning(f"Timeout calling {url}")
        return {"source": "source_name", "found": False, "error": "timeout"}
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP {e.response.status_code} from {url}")
        return {"source": "source_name", "found": False, "error": f"http_{e.response.status_code}"}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"source": "source_name", "found": False, "error": "unexpected"}
```

Never let an external API failure crash the whole verification. Degrade gracefully.

## Lessons (Updated As We Build)

- eyecite requires clean text input — always run `clean_text()` before `get_citations()`
- CourtListener API requires POST with form data, not JSON body
- asyncpg connection pool must be initialized in FastAPI startup event, not at module level
- Redis cache keys: `citation:{normalized_citation_hash}` — use SHA-256 of normalized text

## Phase Status

- [ ] Phase 1: MVP — CourtListener + basic scoring + audit log
- [ ] Phase 2: Professional — LexisNexis + semantic check
- [ ] Phase 3: Enterprise — MENA sources + Compliance Proof Pack PDF

## Core Principles

- Simplicity first. Every change must be as simple as possible.
- No temporary fixes. Find the root cause.
- Only touch what is necessary. No side effects.
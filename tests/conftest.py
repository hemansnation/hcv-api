import pytest
import asyncpg

from api.config import settings
from api.db.queries import create_tables


@pytest.fixture
async def pool():
    """Async asyncpg pool connected to the test database."""
    p = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=3)
    await create_tables(p)
    yield p
    await p.close()

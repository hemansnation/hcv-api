import logging

import asyncpg
from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


async def init_db_pool(
    app: FastAPI,
    database_url: str,
    min_size: int = 5,
    max_size: int = 20,
) -> None:
    """Create asyncpg pool and store on app.state.db_pool."""
    app.state.db_pool = await asyncpg.create_pool(
        database_url,
        min_size=min_size,
        max_size=max_size,
    )
    logger.info("Database pool initialized")


async def close_db_pool(app: FastAPI) -> None:
    """Close the asyncpg pool stored on app.state.db_pool."""
    pool: asyncpg.Pool | None = getattr(app.state, "db_pool", None)
    if pool:
        await pool.close()
        logger.info("Database pool closed")


def get_db_pool(request: Request) -> asyncpg.Pool:
    """FastAPI dependency — returns the asyncpg pool from app.state."""
    return request.app.state.db_pool

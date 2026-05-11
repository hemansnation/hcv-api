import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db.connection import close_db_pool, init_db_pool
from .db.queries import create_tables
from .routes import audit, health, verify

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database and Redis connections during app lifecycle."""

    # --- Startup ---
    try:
        await init_db_pool(
            app,
            settings.database_url,
            min_size=settings.database_pool_min_size,
            max_size=settings.database_pool_max_size,
        )
        await create_tables(app.state.db_pool)
    except Exception as e:
        logger.warning(f"Database not available at startup: {e}")
        app.state.db_pool = None

    try:
        app.state.redis_client = redis.from_url(settings.redis_url)
        await app.state.redis_client.ping()
        logger.info("Redis client initialized")
    except Exception as e:
        logger.warning(f"Redis not available at startup: {e}")
        app.state.redis_client = None

    yield

    # --- Shutdown ---
    await close_db_pool(app)

    redis_client = getattr(app.state, "redis_client", None)
    if redis_client:
        await redis_client.aclose()
        logger.info("Redis client closed")


def create_app() -> FastAPI:
    """FastAPI app factory."""

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Legal citation verification API",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(verify.router, tags=["verify"])
    app.include_router(audit.router, tags=["audit"])

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "status": 500,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "message": exc.detail, "status": exc.status_code},
        )

    return app


app = create_app()

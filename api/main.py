import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db.connection import close_db_pool, init_db_pool
from .db.queries import create_tables
from .routes import audit, health, verify

logger = logging.getLogger(__name__)


class _JsonFormatter(logging.Formatter):
    """Emits each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client_id",
        ):
            if hasattr(record, field):
                log_obj[field] = getattr(record, field)
        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    if settings.app_env == "production":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        handlers=[handler],
        force=True,
    )


_configure_logging()


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
        logger.warning("Database not available at startup: %s", e)
        app.state.db_pool = None

    try:
        app.state.redis_client = redis.from_url(settings.redis_url)
        await app.state.redis_client.ping()
        logger.info("Redis client initialized")
    except Exception as e:
        logger.warning("Redis not available at startup: %s", e)
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

    @app.middleware("http")
    async def request_id_and_logging(request: Request, call_next: Any) -> Any:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.monotonic()

        response = await call_next(request)

        duration_ms = int((time.monotonic() - start) * 1000)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    app.include_router(health.router, tags=["health"])
    app.include_router(verify.router, tags=["verify"])
    app.include_router(audit.router, tags=["audit"])

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled exception on %s %s: %s", request.method, request.url, exc
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "status": 500,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        if isinstance(exc.detail, dict):
            content = exc.detail
        else:
            content = {
                "error": exc.detail,
                "message": exc.detail,
                "status": exc.status_code,
            }
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=exc.headers,
        )

    return app


app = create_app()

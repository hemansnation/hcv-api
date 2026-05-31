import time
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..config import settings

router = APIRouter()

_start_time = time.time()


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    cache: str
    uptime_seconds: int
    timestamp: str


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Returns service status, database connectivity, and cache status."""
    db_pool = getattr(request.app.state, "db_pool", None)
    redis_client = getattr(request.app.state, "redis_client", None)

    database_status = "disconnected"
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            database_status = "connected"
        except Exception:
            database_status = "disconnected"

    cache_status = "disconnected"
    if redis_client:
        try:
            await redis_client.ping()
            cache_status = "connected"
        except Exception:
            cache_status = "disconnected"

    uptime_seconds = int(time.time() - _start_time)
    status = (
        "healthy"
        if database_status == "connected" and cache_status == "connected"
        else "degraded"
    )

    return HealthResponse(
        status=status,
        version=settings.app_version,
        database=database_status,
        cache=cache_status,
        uptime_seconds=uptime_seconds,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )

import os
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["DATABASE_URL"],
            min_size=2,
            max_size=10,
        )
    return _pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await get_pool()
    # Reset all online statuses on startup
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_online = FALSE, updated_at = NOW()")
    print("[startup] Reset all online statuses")
    yield
    if _pool:
        await _pool.close()

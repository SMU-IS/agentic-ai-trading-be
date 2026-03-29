import json
import asyncpg
from app.core.config import env_config
from app.core.logger import logger
from datetime import datetime

_pool = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=env_config.postgres_host,
            port=env_config.postgres_port,
            user=env_config.postgres_user,
            database=env_config.postgres_db,
            min_size=2,
            max_size=10,
            ssl=True
        )
        logger.info("✅ PostgreSQL pool created")
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("🛑 PostgreSQL pool closed")


async def init_db():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id                 TEXT PRIMARY KEY,
                    content_type       TEXT,
                    native_id          TEXT,
                    source             TEXT,
                    author             TEXT,
                    url                TEXT,
                    content            JSONB,
                    engagement         JSONB,
                    metadata           JSONB,
                    images             JSONB,
                    links              JSONB,
                    ticker_metadata    JSONB,
                    sentiment_analysis JSONB,
                    vectorised         BOOLEAN DEFAULT FALSE,
                    created_at         TIMESTAMPTZ,
                    processed_at       TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            logger.info("✅ PostgreSQL table ready")
    except Exception as e:
        logger.error(f"❌ Failed to initialise PostgreSQL table: {e}")


async def save_post(decoded: dict, vectorised: bool = False):
    pool = await get_pool()

    raw_ts = decoded.get("timestamps")
    if isinstance(raw_ts, str):
        try:
            created_at = datetime.fromisoformat(raw_ts)
        except ValueError:
            created_at = None
    elif isinstance(raw_ts, datetime):
        created_at = raw_ts
    else:
        created_at = None

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO posts (
                    id, content_type, native_id, source, author, url,
                    content, engagement, metadata, images, links,
                    ticker_metadata, sentiment_analysis,
                    vectorised, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (id) DO NOTHING
                """,
                decoded.get("id", "").strip('"'),
                decoded.get("content_type"),
                decoded.get("native_id"),
                decoded.get("source"),
                decoded.get("author"),
                decoded.get("url"),
                json.dumps(decoded.get("content", {})),
                json.dumps(decoded.get("engagement", {})),
                json.dumps(decoded.get("metadata", {})),
                json.dumps(decoded.get("images", {})),
                json.dumps(decoded.get("links", {})),
                json.dumps(decoded.get("ticker_metadata", {})),
                json.dumps(decoded.get("sentiment_analysis", {})),
                vectorised,
                created_at,
            )
    except Exception as e:
        logger.error(f"❌ Failed to save post to postgres: {e}")
        raise

async def mark_vectorised(post_id: str):
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE posts SET vectorised = TRUE WHERE id = $1",
                post_id,
            )
    except Exception as e:
        logger.error(f"❌ Failed to mark post as vectorised: {e}")
        raise
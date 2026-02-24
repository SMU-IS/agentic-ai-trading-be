import logging
from typing import AsyncGenerator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.config import env_config

logger = logging.getLogger("uvicorn.error")


class DatabaseManager:
    def __init__(self):
        self.pool: AsyncConnectionPool | None = None
        self.checkpointer: AsyncPostgresSaver | None = None

    async def get_checkpointer(self) -> AsyncGenerator[AsyncPostgresSaver, None]:
        """Manages the lifecycle of the Postgres checkpointer pool."""
        conninfo = (
            f"postgresql://{env_config.postgres_user}:"
            f"{env_config.postgres_password}@rag-bot-conversation-db:5432/"
            f"{env_config.postgres_db}?sslmode=disable"
        )

        try:
            async with AsyncConnectionPool(
                conninfo=conninfo,
                max_size=20,
                kwargs={"autocommit": True, "prepare_threshold": None},
            ) as pool:
                logger.info("🔗 Database connection pool created.")
                self.pool = pool
                self.checkpointer = AsyncPostgresSaver(pool)
                await self.checkpointer.setup()
                logger.info("✅ Checkpointer tables verified/created.")

                yield self.checkpointer
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
            raise


db_manager = DatabaseManager()

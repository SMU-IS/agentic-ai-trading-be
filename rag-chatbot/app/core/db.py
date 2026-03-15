import logging
from typing import AsyncGenerator

from psycopg_pool import AsyncConnectionPool

from app.core.config import env_config
from app.services.bot_memory import BotMemory

logger = logging.getLogger("uvicorn.error")


class DatabaseManager:
    def __init__(self):
        self.pool: AsyncConnectionPool | None = None
        self.checkpointer: BotMemory | None = None

    async def get_checkpointer(self) -> AsyncGenerator[BotMemory, None]:
        """Manages the lifecycle of the Postgres checkpointer pool."""
        conninfo = (
            f"postgresql://{env_config.postgres_user}:"
            f"{env_config.postgres_password}@{env_config.postgres_host}:5432/"
            f"{env_config.postgres_db}?sslmode=require"
        )

        try:
            async with AsyncConnectionPool(
                conninfo=conninfo,
                max_size=20,
                kwargs={"autocommit": True, "prepare_threshold": None},
            ) as pool:
                logger.info("🔗 Database connection pool created.")
                self.pool = pool
                self.checkpointer = BotMemory(pool)
                await self.checkpointer.setup()
                logger.info("✅ Checkpointer Tables Created.")
                logger.info("✅ Thread Views Table Created.")

                yield self.checkpointer
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
            raise


db_manager = DatabaseManager()

import json
from typing import Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class BotMemory(AsyncPostgresSaver):
    """
    Asynchronous optimised version of LangGraph's Postgres saver.

    This class:
    - Extends `AsyncPostgresSaver` to keep using LangGraph's default checkpoint
      storage in Postgres.
    - Adds a lightweight `thread_views` table used for fast sidebar / inbox
      rendering in chat-based applications.

    The `thread_views` table contains:
        thread_id   TEXT PRIMARY KEY
        user_id     TEXT
        title       TEXT
        updated_at  TIMESTAMPTZ
        extra_data  JSONB

    Only one row exists per thread, and it gets updated each time a checkpoint
    is saved for that thread.
    """

    async def setup(self) -> None:
        """
        Asynchronously initializes database schema.

        Steps:
        1. Calls AsyncPostgresSaver.setup() to create LangGraph's default
           checkpoint tables.
        2. Creates the `thread_views` table if missing.
        3. Creates indexes on:
            - user_id      (for fast filtering by user)
            - updated_at   (for sorting recent threads)

        Notes:
        - AsyncPostgresSaver provides the internal `_cursor()` context manager.
        - PostgreSQL automatically commits if the connection uses autocommit.
        """
        await super().setup()

        async with self._cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS thread_views (
                    thread_id   TEXT PRIMARY KEY,
                    user_id     TEXT,
                    title       TEXT,
                    updated_at  TIMESTAMPTZ DEFAULT NOW(),
                    extra_data  JSONB
                );
                """
            )
            await cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_thread_views_user
                ON thread_views(user_id);
                """
            )
            await cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_thread_views_updated
                ON thread_views(updated_at DESC);
                """
            )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: Optional[CheckpointMetadata],
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """
        Asynchronous override of `aput`.

        Responsibilities:
        1. Save checkpoint using AsyncPostgresSaver.aput().
        2. Upsert (insert or update) a summary entry into `thread_views`.

        Metadata merging rules:
        - Metadata comes from:
            a) the `metadata` argument
            b) config["metadata"]
        - Conflicting keys are resolved by giving priority to the
          explicit `metadata` argument.

        Parameters:
        - config: RunnableConfig containing thread_id under config["configurable"]
        - checkpoint: Checkpoint data
        - metadata: Optional metadata passed to graph.ainvoke()
        - new_versions: Channel versioning info

        Returns:
        - RunnableConfig result returned by the parent class.
        """
        result_config = await super().aput(config, checkpoint, metadata, new_versions)

        # Extract and merge metadata
        lg_metadata = metadata or {}
        cfg_metadata = config.get("metadata") or {}
        merged_metadata = {**cfg_metadata, **lg_metadata}

        thread_id = config["configurable"]["thread_id"]
        user_id = merged_metadata.get("user_id")
        title = merged_metadata.get("title")

        # Store all metadata into a JSONB column
        extra_json = json.dumps(merged_metadata)

        query = """
            INSERT INTO thread_views (thread_id, user_id, title, updated_at, extra_data)
            VALUES (%s, %s, %s, NOW(), %s)
            ON CONFLICT (thread_id) DO UPDATE SET
                updated_at = EXCLUDED.updated_at,
                user_id    = COALESCE(EXCLUDED.user_id, thread_views.user_id),
                title      = COALESCE(EXCLUDED.title, thread_views.title),
                extra_data = EXCLUDED.extra_data;
        """

        async with self._cursor() as cur:
            await cur.execute(query, (thread_id, user_id, title, extra_json))

        return result_config

    # ----------------------------------------------------------------------
    # Helper asynchronous functions for retrieving thread lists
    # ----------------------------------------------------------------------
    async def aget_user_threads(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict]:
        """
        Retrieve a paginated list of threads belonging to a specific user.

        Returns:
            A list of dictionaries:
            - thread_id
            - title
            - updated_at
        """
        query = """
            SELECT thread_id, title, updated_at
            FROM thread_views
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
        """

        async with self._cursor() as cur:
            await cur.execute(query, (user_id, limit, offset))
            rows = await cur.fetchall()

        return [
            {
                "thread_id": row["thread_id"],
                "title": row["title"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bot_memory import BotMemory


@pytest.fixture
def mock_cursor():
    cursor = AsyncMock()
    cursor.fetchall.return_value = []
    return cursor


@pytest.fixture
def bot_memory(mock_cursor):
    # Completely mock superclass to avoid langgraph internal connection checks
    with (
        patch(
            "app.services.bot_memory.AsyncPostgresSaver.setup", new_callable=AsyncMock
        ),
        patch("app.services.bot_memory.AsyncPostgresSaver.__init__", return_value=None),
        patch(
            "app.services.bot_memory.AsyncPostgresSaver.aput", new_callable=AsyncMock
        ) as mock_aput,
    ):
        memory = BotMemory(conn=None)
        # Mock _cursor at the instance level
        memory._cursor = MagicMock()
        memory._cursor.return_value.__aenter__.return_value = mock_cursor
        memory.aput_mock = mock_aput  # keep reference
        yield memory


@pytest.mark.asyncio
async def test_setup(bot_memory, mock_cursor):
    await bot_memory.setup()
    calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
    assert any("CREATE TABLE IF NOT EXISTS thread_views" in c for c in calls)


@pytest.mark.asyncio
async def test_aput(bot_memory, mock_cursor):
    config = {
        "configurable": {"thread_id": "t1"},
        "metadata": {"user_id": "u1", "title": "test"},
    }
    checkpoint = {"v": 1, "channel_values": {}}
    metadata = {"user_id": "u1", "title": "test"}
    new_versions = {}

    bot_memory.aput_mock.return_value = config
    await bot_memory.aput(config, checkpoint, metadata, new_versions)

    calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
    assert any("INSERT INTO thread_views" in c for c in calls)


@pytest.mark.asyncio
async def test_aget_user_threads(bot_memory, mock_cursor):
    mock_cursor.fetchall.return_value = [
        {"thread_id": "t1", "title": "title1", "updated_at": "2024-01-01"}
    ]
    threads = await bot_memory.aget_user_threads("u1")
    assert len(threads) == 1
    assert threads[0]["thread_id"] == "t1"

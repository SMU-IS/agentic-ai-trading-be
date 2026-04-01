from fastapi import APIRouter, Depends, Request

from app.core.constant import APIPath
from app.schemas.chat import ThreadResponse
from app.services.bot_memory import BotMemory
from app.utils.decode_jwt import get_current_user_id

router = APIRouter(tags=["Threads"])


def get_bot_memory(request: Request) -> BotMemory:
    """Dependency to get the BotMemory instance from app state."""
    return request.app.state.bot_memory


@router.get(APIPath.THREADS, response_model=list[ThreadResponse])
async def get_user_threads(
    user_id: str = Depends(get_current_user_id),
    limit: int = 20,
    offset: int = 0,
    bot_memory: BotMemory = Depends(get_bot_memory),
):
    """
    Retrieve a paginated list of threads belonging to a specific user.

    Parameters:
    - user_id: The ID of the user whose threads to retrieve
    - limit: Maximum number of threads to return (default: 20)
    - offset: Number of threads to skip for pagination (default: 0)

    Returns:
    - A list of thread objects with thread_id, title, and updated_at
    """
    threads = await bot_memory.aget_user_threads(user_id, limit=limit, offset=offset)
    return threads

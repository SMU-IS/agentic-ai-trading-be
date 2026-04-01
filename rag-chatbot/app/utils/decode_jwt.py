import jwt
from fastapi import Header

from app.utils.logger import setup_logging

logger = setup_logging()


def get_current_user_id(
    x_user_id: str = Header(None, alias="x-user-id"), authorization: str = Header(None)
) -> str:
    """
    Extracts the user identity from either the X-User-Id header (set by Kong)
    or the Authorization Bearer token (extracted manually).
    """

    if x_user_id:
        return x_user_id

    if authorization and authorization.startswith("Bearer "):
        try:
            token = authorization.split(" ")[1]
            payload = jwt.decode(token, options={"verify_signature": False})
            sub = payload.get("sub")
            if sub:
                return sub
        except Exception as e:
            logger.warning(f"Failed to decode JWT for user identification: {e}")

    return "agent-A"

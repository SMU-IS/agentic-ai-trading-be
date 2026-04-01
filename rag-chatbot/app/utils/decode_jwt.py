import jwt
from fastapi import Header
from app.utils.logger import setup_logging

logger = setup_logging()

def get_current_user_id(
    x_user_id: str = Header(None, alias="x-user-id"),
    authorization: str = Header(None)
) -> str:
    """
    Extracts the user identity from either the X-User-Id header (set by Kong)
    or the Authorization Bearer token (extracted manually).
    """
    
    # 1. Primary: Kong already injected the header
    if x_user_id:
        return x_user_id

    # 2. Secondary: Extract 'sub' from the JWT token (useful for local dev/testing)
    if authorization and authorization.startswith("Bearer "):
        try:
            token = authorization.split(" ")[1]
            # No verification needed here since Kong already did it in prod,
            # and in local we just need the identity.
            payload = jwt.decode(token, options={"verify_signature": False})
            sub = payload.get("sub")
            if sub:
                return sub
        except Exception as e:
            logger.warning(f"Failed to decode JWT for user identification: {e}")

    # 3. Final fallback for local development without headers
    return "agent-A"

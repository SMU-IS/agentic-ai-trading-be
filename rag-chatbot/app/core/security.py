from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


# TODO: Helper function
def is_valid(token: str) -> bool:
    return token == "test"


async def get_current_user(auth: HTTPAuthorizationCredentials = Security(security)):
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authentication Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth.credentials

    if not is_valid(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return token

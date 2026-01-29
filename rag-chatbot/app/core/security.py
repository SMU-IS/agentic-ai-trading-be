import jwt
from app.core.config import env_config
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)
SECRET_KEY = env_config.secret_key
ALGORITHM = "HS256"


def verify_token(token: str) -> dict:
    """
    Decodes and verifies the JWT token.
    Returns the token's payload if valid, otherwise raises an exception.
    """

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def get_current_user(auth: HTTPAuthorizationCredentials = Security(security)):
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authentication Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth.credentials
    payload = verify_token(token)

    return payload

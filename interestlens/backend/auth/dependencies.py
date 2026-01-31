"""Authentication dependencies for FastAPI"""

from typing import Optional
from fastapi import Request, HTTPException, status

from .jwt import decode_access_token


async def get_current_user(request: Request) -> dict:
    """
    Get the current authenticated user from the JWT token.
    Raises HTTPException if not authenticated.
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name"),
        "picture": payload.get("picture")
    }


async def get_optional_user(request: Request) -> Optional[dict]:
    """
    Get the current user if authenticated, None otherwise.
    Used for endpoints that work in both authenticated and limited mode.
    """
    try:
        return await get_current_user(request)
    except HTTPException:
        return None

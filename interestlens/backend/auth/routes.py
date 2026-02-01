"""Google OAuth authentication routes"""

import os
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import httpx

from .jwt import create_access_token
from services.redis_client import get_redis
from models.profile import UserProfile
from models.requests import TokenRequest

router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


@router.get("/google")
async def google_login(request: Request):
    """Initiate Google OAuth flow"""
    redirect_uri = str(request.url_for("google_callback"))

    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={redirect_uri}&"
        "response_type=code&"
        "scope=openid%20email%20profile&"
        "access_type=offline"
    )

    return RedirectResponse(url=google_auth_url)


@router.get("/callback")
async def google_callback(code: str, request: Request):
    """Handle Google OAuth callback"""
    redirect_uri = str(request.url_for("google_callback"))

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange code for token"
        )

    tokens = token_response.json()
    id_token_jwt = tokens.get("id_token")

    # Verify and decode the ID token
    try:
        idinfo = id_token.verify_oauth2_token(
            id_token_jwt,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ID token: {e}"
        )

    # Extract user info
    user_id = f"google_{idinfo['sub']}"
    email = idinfo.get("email")
    name = idinfo.get("name")
    picture = idinfo.get("picture")

    # Get or create user profile in Redis
    redis = await get_redis()
    profile_key = f"user:{user_id}"
    existing_profile = await redis.json().get(profile_key)

    if not existing_profile:
        # Create new profile
        profile = UserProfile(
            user_id=user_id,
            email=email,
            name=name
        )
        await redis.json().set(profile_key, "$", profile.model_dump())
        profile_exists = False
    else:
        profile_exists = True

    # Create JWT
    access_token = create_access_token({
        "sub": user_id,
        "email": email,
        "name": name,
        "picture": picture
    })

    # Redirect to frontend with token
    redirect_url = (
        f"{FRONTEND_URL}/auth/callback?"
        f"token={access_token}&"
        f"profile_exists={str(profile_exists).lower()}"
    )

    return RedirectResponse(url=redirect_url)


@router.get("/me")
async def get_current_user_info(request: Request):
    """Get current user info from JWT"""
    from .dependencies import get_current_user

    user = await get_current_user(request)

    # Get full profile from Redis
    redis = await get_redis()
    profile_data = await redis.json().get(f"user:{user['id']}")

    return {
        "user": user,
        "profile": profile_data
    }


@router.post("/logout")
async def logout():
    """Logout - client should clear stored token"""
    return {"status": "ok", "message": "Logged out"}


@router.post("/token")
async def create_token(request: TokenRequest):
    """Create a JWT token for the given user data"""
    token_data = {"sub": request.user_id}

    if request.email:
        token_data["email"] = request.email
    if request.name:
        token_data["name"] = request.name
    if request.picture:
        token_data["picture"] = request.picture

    access_token = create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

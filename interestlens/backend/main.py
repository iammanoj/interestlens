"""
InterestLens Backend API
FastAPI server with Google Cloud ADK agents, Redis, and Weave observability
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

import weave
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Import routers
from auth.routes import router as auth_router
from voice.routes import router as voice_router
from agents.pipeline import analyze_page_pipeline
from services.redis_client import get_redis, init_redis
from models.requests import AnalyzePageRequest, EventRequest
from models.responses import AnalyzePageResponse, EventResponse
from auth.dependencies import get_current_user, get_optional_user

# Initialize Weave for observability
weave.init(os.getenv("WANDB_PROJECT", "interestlens"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup"""
    await init_redis()
    yield


app = FastAPI(
    title="InterestLens API",
    description="AI-powered content personalization for the web",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
        "chrome-extension://*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(voice_router, prefix="/voice", tags=["Voice Onboarding"])


@app.get("/")
async def root():
    return {"message": "InterestLens API", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/analyze_page", response_model=AnalyzePageResponse)
@weave.op()
async def analyze_page(
    request: AnalyzePageRequest,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Analyze a page and return scored items.
    Works in limited mode without auth (no personalization).
    """
    user_id = user["id"] if user else None

    result = await analyze_page_pipeline(
        page_url=request.page_url,
        dom_outline=request.dom_outline,
        items=request.items,
        screenshot_base64=request.screenshot_base64,
        user_id=user_id
    )

    return result


@app.post("/event", response_model=EventResponse)
@weave.op()
async def log_event(
    request: EventRequest,
    user: dict = Depends(get_current_user)
):
    """
    Log a user interaction event (click, dwell, thumbs up/down).
    Requires authentication.
    """
    from services.profile import update_user_profile

    await update_user_profile(
        user_id=user["id"],
        event_type=request.event,
        item_data=request.item_data
    )

    return EventResponse(
        status="ok",
        profile_updated=True
    )


@app.post("/preview_url")
@weave.op()
async def preview_url(url: str, user: Optional[dict] = Depends(get_optional_user)):
    """
    Fetch a rich preview for a URL using Browserbase + Stagehand.
    """
    from services.browserbase import fetch_url_preview

    preview = await fetch_url_preview(url)
    return preview


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

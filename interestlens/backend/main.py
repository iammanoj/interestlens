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
from models.authenticity import (
    AuthenticityCheckRequest,
    AuthenticityCheckResponse,
    BatchAuthenticityRequest,
    BatchAuthenticityResponse
)
from auth.dependencies import get_current_user, get_optional_user

# Initialize Weave for observability (optional - skip if not configured)
WEAVE_ENABLED = False
try:
    wandb_key = os.getenv("WANDB_API_KEY", "")
    # W&B API keys must be at least 40 characters
    if wandb_key and len(wandb_key) >= 40 and wandb_key != "your-wandb-api-key":
        project_name = os.getenv("WANDB_PROJECT", "interestlens")
        weave.init(project_name)
        WEAVE_ENABLED = True
        print(f"Weave initialized for project: {project_name}")
    else:
        print("Weave not configured - API key missing or invalid (needs 40+ chars)")
        print("Get your API key from: https://wandb.ai/authorize")
except Exception as e:
    print(f"Weave init skipped: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup"""
    try:
        await init_redis()
        print("Redis connected successfully")
    except Exception as e:
        print(f"Redis not available - running without caching: {e}")
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
    user: Optional[dict] = Depends(get_optional_user),
    check_authenticity: bool = True
):
    """
    Analyze a page and return scored items.
    Works in limited mode without auth (no personalization).
    Set check_authenticity=true to run authenticity checks on news items.
    """
    user_id = user["id"] if user else None

    result = await analyze_page_pipeline(
        page_url=request.page_url,
        dom_outline=request.dom_outline,
        items=request.items,
        screenshot_base64=request.screenshot_base64,
        user_id=user_id,
        check_authenticity=check_authenticity
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


# ============= Authenticity Endpoints =============

@app.post("/check_authenticity", response_model=AuthenticityCheckResponse)
@weave.op()
async def check_authenticity(
    request: AuthenticityCheckRequest,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Check authenticity of a single article.
    Extracts claims and verifies against cross-reference sources.
    """
    from agents.authenticity import authenticity_agent

    result = await authenticity_agent(
        item_id=request.item_id,
        url=request.url,
        text=request.text,
        check_depth=request.check_depth
    )

    return AuthenticityCheckResponse(
        item_id=result.item_id,
        authenticity_score=result.authenticity_score,
        confidence=result.confidence,
        verification_status=result.verification_status,
        sources_checked=result.sources_checked,
        corroborating_count=result.corroborating_count,
        conflicting_count=result.conflicting_count,
        explanation=result.explanation,
        checked_at=result.checked_at,
        processing_time_ms=result.processing_time_ms
    )


@app.post("/check_authenticity/batch", response_model=BatchAuthenticityResponse)
@weave.op()
async def check_authenticity_batch(
    request: BatchAuthenticityRequest,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Batch authenticity check for multiple items.
    Runs checks in parallel for performance.
    """
    from agents.authenticity import authenticity_agent
    import asyncio
    import time

    start_time = time.time()
    semaphore = asyncio.Semaphore(request.max_concurrent)

    async def check_one(item: AuthenticityCheckRequest):
        async with semaphore:
            result = await authenticity_agent(
                item_id=item.item_id,
                url=item.url,
                text=item.text,
                check_depth=item.check_depth
            )
            return AuthenticityCheckResponse(
                item_id=result.item_id,
                authenticity_score=result.authenticity_score,
                confidence=result.confidence,
                verification_status=result.verification_status,
                sources_checked=result.sources_checked,
                corroborating_count=result.corroborating_count,
                conflicting_count=result.conflicting_count,
                explanation=result.explanation,
                checked_at=result.checked_at,
                processing_time_ms=result.processing_time_ms
            )

    results = await asyncio.gather(
        *[check_one(item) for item in request.items],
        return_exceptions=True
    )

    valid_results = [r for r in results if isinstance(r, AuthenticityCheckResponse)]

    return BatchAuthenticityResponse(
        results=valid_results,
        total_processing_time_ms=int((time.time() - start_time) * 1000)
    )


@app.get("/authenticity_status/{item_id}")
@weave.op()
async def get_authenticity_status(item_id: str):
    """
    Get the authenticity check status/result for an item.
    Returns cached result if available.
    """
    from services.redis_client import get_cached_authenticity

    result = await get_cached_authenticity(item_id)

    if result:
        return {
            "status": "completed",
            "item_id": item_id,
            "result": result
        }

    return {
        "status": "not_found",
        "item_id": item_id,
        "message": "No authenticity check found for this item"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

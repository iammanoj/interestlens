"""Activity tracking routes for InterestLens."""

import time
from typing import Optional, List
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Request

from auth.dependencies import get_optional_user
from services.redis_client import get_redis, json_get, json_set
from activity.models import (
    TrackActivityRequest,
    TrackActivityResponse,
    ActivityHistoryRequest,
    ActivityHistoryResponse,
    Activity,
    DomainStats,
    CategoryStats
)

router = APIRouter()

# Constants
ACTIVITY_TTL = 60 * 60 * 24 * 30  # 30 days
MAX_ACTIVITIES_PER_USER = 10000
CATEGORY_AFFINITY_WEIGHT = 0.1


def get_user_id(user: Optional[dict], request: Request) -> str:
    """Get user ID from auth or generate anonymous ID from IP."""
    if user and user.get("id"):
        return user["id"]
    # Use client IP hash for anonymous users
    client_ip = request.client.host if request.client else "unknown"
    return f"anon_{hash(client_ip) % 10000000}"


@router.post("/track", response_model=TrackActivityResponse)
async def track_activity(
    data: TrackActivityRequest,
    request: Request,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Track user browsing activities.

    Accepts batched activities from the Chrome extension including:
    - Page visits with time spent and detected categories
    - Click interactions on links and articles

    Activities are stored in Redis and used to refine user interests.
    """
    user_id = data.user_id or get_user_id(user, request)
    redis = await get_redis()

    if not redis:
        # Still return success - activity tracking is best-effort
        return TrackActivityResponse(
            status="ok",
            activities_processed=len(data.activities),
            categories_updated=[]
        )

    activities_key = f"activity:{user_id}"
    profile_key = f"user:{user_id}"

    # Get existing activities
    existing_data = await json_get(activities_key) or {"activities": [], "stats": {}}
    activities_list = existing_data.get("activities", [])

    # Category tracking for profile updates
    category_times = defaultdict(int)
    domain_times = defaultdict(int)
    categories_seen = set()

    # Process new activities
    for activity in data.activities:
        activity_dict = activity.model_dump()

        # Add to list (with size limit)
        activities_list.append(activity_dict)
        if len(activities_list) > MAX_ACTIVITIES_PER_USER:
            activities_list = activities_list[-MAX_ACTIVITIES_PER_USER:]

        # Track categories and time spent
        if activity.type == "page_visit":
            page_data = activity.data
            time_spent = page_data.get("timeSpent", 0)
            categories = page_data.get("categories", [])
            domain = page_data.get("domain", activity.sourceDomain)

            for category in categories:
                category = category.lower().strip()
                if category:
                    category_times[category] += time_spent
                    categories_seen.add(category)

            if domain:
                domain_times[domain] += time_spent

        elif activity.type == "click":
            click_data = activity.data
            # Clicks indicate strong interest
            if click_data.get("isArticleLink"):
                # Could extract categories from click target
                pass

    # Update stats
    existing_stats = existing_data.get("stats", {})
    domain_stats = existing_stats.get("domains", {})
    category_stats = existing_stats.get("categories", {})

    for domain, time_spent in domain_times.items():
        if domain not in domain_stats:
            domain_stats[domain] = {"visits": 0, "time": 0}
        domain_stats[domain]["visits"] += 1
        domain_stats[domain]["time"] += time_spent

    for category, time_spent in category_times.items():
        if category not in category_stats:
            category_stats[category] = {"visits": 0, "time": 0}
        category_stats[category]["visits"] += 1
        category_stats[category]["time"] += time_spent

    # Save activities
    await json_set(activities_key, "$", {
        "activities": activities_list,
        "stats": {
            "domains": domain_stats,
            "categories": category_stats
        },
        "updated_at": int(time.time() * 1000)
    })
    await redis.expire(activities_key, ACTIVITY_TTL)

    # Update user profile with category affinities
    if categories_seen:
        await update_profile_from_activity(profile_key, category_times)

    return TrackActivityResponse(
        status="ok",
        activities_processed=len(data.activities),
        categories_updated=list(categories_seen)
    )


async def update_profile_from_activity(
    profile_key: str,
    category_times: dict
):
    """
    Update user profile topic affinities based on activity.

    Time spent on categories increases affinity, with diminishing returns.
    """
    profile_data = await json_get(profile_key)

    if not profile_data:
        # Create minimal profile
        profile_data = {
            "topic_affinity": {},
            "interaction_count": 0,
            "voice_onboarding_complete": False
        }

    topic_affinity = profile_data.get("topic_affinity", {})

    # Update affinities based on time spent
    for category, time_ms in category_times.items():
        current = topic_affinity.get(category, 0.0)

        # Calculate increment based on time (diminishing returns)
        # 1 minute = 0.1 affinity, up to max 0.5 per session
        time_minutes = time_ms / 60000
        increment = min(0.5, time_minutes * CATEGORY_AFFINITY_WEIGHT)

        # Apply increment with decay towards max
        MAX_AFFINITY = 2.0
        new_value = current + increment * (1 - current / MAX_AFFINITY)
        topic_affinity[category] = min(MAX_AFFINITY, new_value)

    profile_data["topic_affinity"] = topic_affinity
    profile_data["interaction_count"] = profile_data.get("interaction_count", 0) + 1

    await json_set(profile_key, "$", profile_data)


@router.get("/history", response_model=ActivityHistoryResponse)
async def get_activity_history(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    type_filter: Optional[str] = None,
    domain_filter: Optional[str] = None,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Get user's activity history.

    Returns recent activities along with aggregated stats by domain
    and category.
    """
    user_id = get_user_id(user, request)
    redis = await get_redis()

    if not redis:
        return ActivityHistoryResponse()

    activities_key = f"activity:{user_id}"
    data = await json_get(activities_key)

    if not data:
        return ActivityHistoryResponse()

    activities_list = data.get("activities", [])
    stats = data.get("stats", {})

    # Apply filters
    filtered = activities_list
    if type_filter:
        filtered = [a for a in filtered if a.get("type") == type_filter]
    if domain_filter:
        filtered = [a for a in filtered if a.get("sourceDomain") == domain_filter]

    # Apply pagination (newest first)
    filtered = list(reversed(filtered))
    total_count = len(filtered)
    filtered = filtered[offset:offset + limit]

    # Convert to Activity models
    activities = [Activity(**a) for a in filtered]

    # Build domain stats
    domain_data = stats.get("domains", {})
    domain_stats = [
        DomainStats(
            domain=d,
            visit_count=s.get("visits", 0),
            total_time_spent=s.get("time", 0),
            categories=[],
            last_visit=0
        )
        for d, s in sorted(
            domain_data.items(),
            key=lambda x: x[1].get("time", 0),
            reverse=True
        )[:20]
    ]

    # Build category stats
    category_data = stats.get("categories", {})
    category_stats = [
        CategoryStats(
            category=c,
            visit_count=s.get("visits", 0),
            total_time_spent=s.get("time", 0),
            domains=[]
        )
        for c, s in sorted(
            category_data.items(),
            key=lambda x: x[1].get("time", 0),
            reverse=True
        )[:20]
    ]

    # Top categories
    top_categories = [c.category for c in category_stats[:10]]

    return ActivityHistoryResponse(
        activities=activities,
        total_count=total_count,
        domain_stats=domain_stats,
        category_stats=category_stats,
        top_categories=top_categories
    )


@router.delete("/history")
async def clear_activity_history(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user)
):
    """Clear user's activity history."""
    user_id = get_user_id(user, request)
    redis = await get_redis()

    if redis:
        activities_key = f"activity:{user_id}"
        await redis.delete(activities_key)

    return {"status": "cleared", "user_id": user_id}


@router.get("/categories")
async def get_learned_categories(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Get categories learned from user's browsing activity.

    Returns categories ranked by time spent and visit frequency.
    """
    user_id = get_user_id(user, request)
    redis = await get_redis()

    if not redis:
        return {"categories": [], "top_interests": []}

    activities_key = f"activity:{user_id}"
    profile_key = f"user:{user_id}"

    # Get activity stats
    activity_data = await json_get(activities_key)
    category_stats = activity_data.get("stats", {}).get("categories", {}) if activity_data else {}

    # Get profile affinities
    profile_data = await json_get(profile_key)
    topic_affinities = profile_data.get("topic_affinity", {}) if profile_data else {}

    # Combine into ranked list
    categories = []
    for category, stats in category_stats.items():
        affinity = topic_affinities.get(category, 0)
        categories.append({
            "category": category,
            "visits": stats.get("visits", 0),
            "time_spent_ms": stats.get("time", 0),
            "affinity": round(affinity, 3),
            "source": "activity"
        })

    # Add any categories from voice onboarding not in activity
    voice_prefs = profile_data.get("voice_preferences", {}) if profile_data else {}
    if voice_prefs and voice_prefs.get("topics"):
        for topic in voice_prefs["topics"]:
            topic_name = topic.get("topic", "").lower()
            if topic_name and topic_name not in category_stats:
                affinity = topic_affinities.get(topic_name, 0)
                sentiment = topic.get("sentiment", "neutral")
                categories.append({
                    "category": topic_name,
                    "visits": 0,
                    "time_spent_ms": 0,
                    "affinity": round(affinity, 3),
                    "source": "voice",
                    "sentiment": sentiment
                })

    # Sort by affinity
    categories.sort(key=lambda x: abs(x.get("affinity", 0)), reverse=True)

    # Top interests (positive affinity only)
    top_interests = [
        c["category"] for c in categories
        if c.get("affinity", 0) > 0
    ][:10]

    return {
        "categories": categories[:50],
        "top_interests": top_interests
    }

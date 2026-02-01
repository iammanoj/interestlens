"""User profile management"""

from typing import Optional, List
from services.redis_client import get_redis, json_get, json_set
from models.profile import UserProfile


async def get_user_profile(user_id: str) -> Optional[UserProfile]:
    """
    Get user profile from Redis.
    Includes voice preferences if voice onboarding was completed.
    """
    data = await json_get(f"user:{user_id}")

    if data:
        return UserProfile(**data)
    return None



async def save_user_profile(profile: UserProfile):
    """Save user profile to Redis"""
    await json_set(f"user:{profile.user_id}", "$", profile.model_dump())


async def update_user_profile(user_id: str, event_type: str, item_data):
    """
    Update user profile based on an interaction event.
    Uses EMA (Exponential Moving Average) for embeddings.
    Creates a new profile if one doesn't exist.

    Args:
        user_id: The user's ID
        event_type: Type of event (click, thumbs_up, thumbs_down, dwell)
        item_data: ItemData Pydantic model or dict with topics and optional embedding
    """
    profile = await get_user_profile(user_id)
    if not profile:
        # Create a new profile for this user
        profile = UserProfile(user_id=user_id)

    alpha = 0.85  # Decay factor for EMA

    # Handle both Pydantic model and dict
    if hasattr(item_data, 'model_dump'):
        # Pydantic model - convert to dict
        data = item_data.model_dump()
    elif hasattr(item_data, 'topics'):
        # Direct attribute access
        data = {"topics": item_data.topics, "embedding": getattr(item_data, 'embedding', None)}
    else:
        # Already a dict
        data = item_data

    # Update topic affinity
    topics = data.get("topics", [])
    for topic in topics:
        current = profile.topic_affinity.get(topic, 0.0)

        if event_type == "click":
            profile.topic_affinity[topic] = current + 0.3
        elif event_type == "thumbs_up":
            profile.topic_affinity[topic] = current + 0.5
        elif event_type == "thumbs_down":
            profile.topic_affinity[topic] = current - 0.3
        elif event_type == "dwell":
            profile.topic_affinity[topic] = current + 0.1

    # Update embedding vector (EMA)
    embedding = data.get("embedding")
    if embedding and event_type in ["click", "thumbs_up", "dwell"]:
        if profile.user_text_vector:
            # EMA update
            profile.user_text_vector = [
                alpha * old + (1 - alpha) * new
                for old, new in zip(profile.user_text_vector, embedding)
            ]
        else:
            # First embedding
            profile.user_text_vector = embedding

    profile.interaction_count += 1
    await save_user_profile(profile)

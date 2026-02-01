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


async def update_user_profile(user_id: str, event_type: str, item_data: dict):
    """
    Update user profile based on an interaction event.
    Uses EMA (Exponential Moving Average) for embeddings.
    """
    profile = await get_user_profile(user_id)
    if not profile:
        return

    alpha = 0.85  # Decay factor for EMA

    # Update topic affinity
    topics = item_data.get("topics", [])
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
    embedding = item_data.get("embedding")
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

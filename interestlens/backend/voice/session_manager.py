"""
Session lifecycle management for voice onboarding.
Handles starting/stopping bots, Redis session tracking, and cleanup.
"""

import os
import asyncio
import time
import json
from typing import Dict, Optional
from dataclasses import dataclass, asdict
import httpx

from services.redis_client import (
    get_redis, json_get, json_set, json_set_field,
    get_transcription_history, update_extracted_categories,
    mark_final_extraction_complete
)
from models.profile import VoicePreferences, ExtractedCategories
from voice.category_extraction import (
    extract_categories_comprehensive,
    merge_category_extractions,
    categories_to_dict,
    dict_to_categories
)


DAILY_API_KEY = os.getenv("DAILY_API_KEY")
DAILY_DOMAIN = os.getenv("DAILY_DOMAIN", "interestlens.daily.co")

# Session timeout (30 minutes)
SESSION_TIMEOUT = 1800

# Maximum number of concurrent sessions to prevent memory leaks
MAX_ACTIVE_SESSIONS = 100

# In-memory session tracking (for bot processes)
# In production, this would be replaced with proper process management
_active_sessions: Dict[str, dict] = {}
_session_lock = asyncio.Lock()


@dataclass
class SessionInfo:
    """Information about an active voice session."""
    room_name: str
    user_id: str
    room_url: str
    created_at: float
    last_activity: float
    status: str  # "starting", "active", "ending", "ended"
    bot_token: Optional[str] = None
    preferences: Optional[dict] = None


async def start_bot_for_session(
    room_name: str,
    room_url: str,
    user_id: str
) -> SessionInfo:
    """
    Start a Pipecat bot for a voice session.

    Args:
        room_name: The Daily room name
        room_url: The Daily room URL
        user_id: The user's ID

    Returns:
        SessionInfo with session details

    Raises:
        RuntimeError: If max sessions limit is reached
    """
    async with _session_lock:
        # Check if session already exists
        if room_name in _active_sessions:
            existing = _active_sessions[room_name]
            if existing["status"] in ["starting", "active"]:
                return SessionInfo(**existing)

        # Check max sessions limit to prevent memory leaks
        active_count = len([s for s in _active_sessions.values() if s["status"] in ["starting", "active"]])
        if active_count >= MAX_ACTIVE_SESSIONS:
            raise RuntimeError(f"Maximum concurrent sessions ({MAX_ACTIVE_SESSIONS}) reached. Please try again later.")

        # Create bot token
        bot_token = await create_bot_token(room_name)

        # Create session info
        session = SessionInfo(
            room_name=room_name,
            user_id=user_id,
            room_url=room_url,
            created_at=time.time(),
            last_activity=time.time(),
            status="starting",
            bot_token=bot_token
        )

        # Store in memory
        _active_sessions[room_name] = asdict(session)

        # Store in Redis for persistence
        await store_session_in_redis(session)

    # Start bot in background
    asyncio.create_task(run_bot_process(session))

    return session


async def create_bot_token(room_name: str) -> Optional[str]:
    """Create a Daily meeting token for the bot."""
    if not DAILY_API_KEY:
        return None

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.daily.co/v1/meeting-tokens",
            headers={"Authorization": f"Bearer {DAILY_API_KEY}"},
            json={
                "properties": {
                    "room_name": room_name,
                    "user_id": "onboarding-bot",
                    "user_name": "InterestLens Assistant",
                    "is_owner": True,  # Required for transcription
                    "enable_recording": False,
                }
            }
        )

        if response.status_code == 200:
            return response.json()["token"]
        else:
            print(f"Failed to create bot token: {response.text}")
            return None


async def run_bot_process(session: SessionInfo):
    """
    Run the Pipecat bot for a session.

    In production, this would spawn a separate process.
    For hackathon, we run it in the same process.
    """
    from voice.pipeline import run_voice_bot
    from voice.websocket import (
        get_preference_update_callback,
        get_session_complete_callback,
        get_transcription_callback,
        manager as ws_manager
    )

    try:
        # Update status
        async with _session_lock:
            if session.room_name in _active_sessions:
                _active_sessions[session.room_name]["status"] = "active"

        # Create callbacks for WebSocket updates
        on_update = get_preference_update_callback(session.room_name)
        on_complete = get_session_complete_callback(session.room_name)
        on_transcript = get_transcription_callback(session.room_name)

        # Wrap the completion callback to also save preferences
        # IMPORTANT: Always send WebSocket notification even if save fails
        async def on_session_complete(preferences: VoicePreferences):
            print(f"[SESSION_MANAGER] Session complete callback triggered for {session.room_name}")
            try:
                await save_session_preferences(session.room_name, session.user_id, preferences)
                print(f"[SESSION_MANAGER] Preferences saved successfully for {session.room_name}")
            except Exception as e:
                print(f"[SESSION_MANAGER] Failed to save preferences: {e}")
            # ALWAYS send WebSocket notification, even if save fails
            print(f"[SESSION_MANAGER] Sending session_complete WebSocket notification for {session.room_name}")
            await on_complete(preferences)

        # Run the bot
        await run_voice_bot(
            room_url=session.room_url,
            room_token=session.bot_token,
            user_id=session.user_id,
            room_name=session.room_name,
            on_preferences_update=on_update,
            on_session_complete=on_session_complete,
            on_transcription=on_transcript
        )

    except Exception as e:
        print(f"Bot process error for {session.room_name}: {e}")
        await ws_manager.send_error(session.room_name, str(e))

    finally:
        # Cleanup
        await end_session(session.room_name)


async def save_session_preferences(room_name: str, user_id: str, preferences: VoicePreferences):
    """
    Save extracted preferences to user profile.
    Also performs comprehensive category extraction at session end.
    Creates a new profile if one doesn't exist.
    """
    redis = await get_redis()
    if not redis:
        print(f"[VOICE] Redis not available, cannot save preferences for {user_id}")
        return

    from models.profile import UserProfile

    profile_key = f"user:{user_id}"
    profile_data = await json_get(profile_key)

    if not profile_data:
        # Create new profile for this user
        print(f"[VOICE] Creating new profile for user {user_id}")
        profile = UserProfile(user_id=user_id)
    else:
        profile = UserProfile(**profile_data)

    # Get transcription history and perform comprehensive extraction
    session_id = room_name  # room_name is used as session_id
    transcription_data = await get_transcription_history(user_id, session_id)

    extracted_categories = ExtractedCategories()
    if transcription_data and transcription_data.get("messages"):
        try:
            # Perform comprehensive extraction on full transcript
            comprehensive_categories = await extract_categories_comprehensive(
                transcription_data["messages"]
            )

            # Get existing incremental categories
            existing_categories_data = transcription_data.get("extracted_categories", {})
            if existing_categories_data.get("likes") or existing_categories_data.get("dislikes"):
                existing_categories = dict_to_categories(existing_categories_data)
                # Merge incremental and comprehensive extractions
                extracted_categories = merge_category_extractions(
                    existing_categories,
                    comprehensive_categories
                )
            else:
                extracted_categories = comprehensive_categories

            # Update Redis with final merged categories
            await update_extracted_categories(
                user_id=user_id,
                session_id=session_id,
                categories=categories_to_dict(extracted_categories)
            )

            # Mark final extraction as complete
            await mark_final_extraction_complete(user_id, session_id)

            print(f"Comprehensive extraction complete: {len(extracted_categories.likes)} likes, {len(extracted_categories.dislikes)} dislikes")

        except Exception as e:
            print(f"Comprehensive extraction error: {e}")

    # Apply voice preferences to topic affinities
    for topic_pref in preferences.topics:
        weight = topic_pref.intensity
        if topic_pref.sentiment == "dislike":
            weight = -weight
        elif topic_pref.sentiment == "neutral":
            weight = 0

        profile.topic_affinity[topic_pref.topic] = weight

        # Add subtopic preferences
        for subtopic in topic_pref.subtopics:
            profile.topic_affinity[subtopic] = weight * 0.8
        for avoid in topic_pref.avoid_subtopics:
            profile.topic_affinity[avoid] = -abs(weight) * 0.5

    # Also apply extracted categories to topic affinities
    for like in extracted_categories.likes:
        current = profile.topic_affinity.get(like.category, 0.0)
        # Use intensity as weight, max with existing
        profile.topic_affinity[like.category] = max(current, like.intensity)
        # Add subtopics
        for subtopic in like.subtopics:
            profile.topic_affinity[subtopic] = like.intensity * 0.8

    for dislike in extracted_categories.dislikes:
        current = profile.topic_affinity.get(dislike.category, 0.0)
        # Use negative intensity as weight, min with existing
        profile.topic_affinity[dislike.category] = min(current, -dislike.intensity)
        # Add subtopics
        for subtopic in dislike.subtopics:
            profile.topic_affinity[subtopic] = -dislike.intensity * 0.8

    # IMPORTANT: Populate voice_preferences.topics from extracted_categories if empty
    # This ensures the scoring algorithm can use voice_modifier (30% weight)
    # The category extraction is more reliable than extract_final_preferences
    from models.profile import TopicPreference
    if not preferences.topics and (extracted_categories.likes or extracted_categories.dislikes):
        print(f"[VOICE] Populating voice_preferences.topics from extracted_categories")
        for like in extracted_categories.likes:
            preferences.topics.append(TopicPreference(
                topic=like.category,
                sentiment="like",
                intensity=like.intensity,
                subtopics=like.subtopics,
                avoid_subtopics=[]
            ))
        for dislike in extracted_categories.dislikes:
            preferences.topics.append(TopicPreference(
                topic=dislike.category,
                sentiment="dislike",
                intensity=dislike.intensity,
                subtopics=dislike.subtopics,
                avoid_subtopics=[]
            ))
        print(f"[VOICE] voice_preferences now has {len(preferences.topics)} topics")

    profile.voice_onboarding_complete = True
    profile.voice_preferences = preferences

    await json_set(profile_key, "$", profile.model_dump())
    print(f"Saved preferences for user {user_id}: {len(preferences.topics)} topics, {len(extracted_categories.likes)} category likes, {len(extracted_categories.dislikes)} category dislikes")


async def end_session(room_name: str):
    """
    End a voice session and cleanup resources.

    Args:
        room_name: The Daily room name
    """
    async with _session_lock:
        if room_name in _active_sessions:
            _active_sessions[room_name]["status"] = "ended"
            del _active_sessions[room_name]

    # Remove from Redis
    redis = await get_redis()
    if redis:
        await redis.delete(f"voice_session:{room_name}")

    # Optionally delete the Daily room
    await delete_daily_room(room_name)


async def delete_daily_room(room_name: str):
    """Delete a Daily room."""
    if not DAILY_API_KEY:
        return

    try:
        async with httpx.AsyncClient() as client:
            await client.delete(
                f"https://api.daily.co/v1/rooms/{room_name}",
                headers={"Authorization": f"Bearer {DAILY_API_KEY}"}
            )
    except Exception as e:
        print(f"Failed to delete Daily room {room_name}: {e}")


async def store_session_in_redis(session: SessionInfo):
    """Store session info in Redis for persistence."""
    redis = await get_redis()
    if not redis:
        return

    key = f"voice_session:{session.room_name}"
    await json_set(key, "$", asdict(session))
    await redis.expire(key, SESSION_TIMEOUT)


async def get_session_status(room_name: str) -> dict:
    """
    Get the current status of a voice session.

    Args:
        room_name: The Daily room name

    Returns:
        Dict with session status and preferences
    """
    import time
    current_time = time.time()

    # Check in-memory first
    async with _session_lock:
        if room_name in _active_sessions:
            session = _active_sessions[room_name]
            # Check if session is stale
            last_activity = session.get("last_activity", 0)
            if current_time - last_activity > SESSION_TIMEOUT:
                return {
                    "exists": False,
                    "status": "expired",
                    "error": "SESSION_EXPIRED",
                    "message": "Session has expired. Please start a new session.",
                    "created_at": session.get("created_at"),
                    "last_activity": last_activity,
                    "preferences": session.get("preferences")
                }
            return {
                "exists": True,
                "status": session["status"],
                "created_at": session["created_at"],
                "last_activity": session["last_activity"],
                "preferences": session.get("preferences")
            }

    # Check Redis
    session_data = await json_get(f"voice_session:{room_name}")
    if session_data:
        # Check if Redis session is stale
        last_activity = session_data.get("last_activity", 0)
        if current_time - last_activity > SESSION_TIMEOUT:
            return {
                "exists": False,
                "status": "expired",
                "error": "SESSION_EXPIRED",
                "message": "Session has expired. Please start a new session.",
                "created_at": session_data.get("created_at"),
                "last_activity": last_activity,
                "preferences": session_data.get("preferences")
            }
        return {
            "exists": True,
            "status": session_data.get("status", "unknown"),
            "created_at": session_data.get("created_at"),
            "last_activity": session_data.get("last_activity"),
            "preferences": session_data.get("preferences")
        }

    return {
        "exists": False,
        "status": "not_found",
        "error": "SESSION_NOT_FOUND",
        "message": "Session not found. It may have been cleaned up or never existed.",
        "created_at": None,
        "last_activity": None,
        "preferences": None
    }


async def update_session_activity(room_name: str):
    """Update the last activity time for a session."""
    async with _session_lock:
        if room_name in _active_sessions:
            _active_sessions[room_name]["last_activity"] = time.time()

    redis = await get_redis()
    if redis:
        key = f"voice_session:{room_name}"
        await json_set_field(key, "last_activity", time.time())
        await redis.expire(key, SESSION_TIMEOUT)


async def update_session_preferences(room_name: str, preferences: VoicePreferences):
    """Update the preferences for a session (for live tracking)."""
    async with _session_lock:
        if room_name in _active_sessions:
            _active_sessions[room_name]["preferences"] = preferences.model_dump()
            _active_sessions[room_name]["last_activity"] = time.time()

    key = f"voice_session:{room_name}"
    await json_set_field(key, "preferences", preferences.model_dump())
    await json_set_field(key, "last_activity", time.time())


async def cleanup_stale_sessions():
    """
    Cleanup sessions that have been inactive for too long.
    Should be called periodically (e.g., every 5 minutes).
    """
    current_time = time.time()
    stale_rooms = []

    async with _session_lock:
        for room_name, session in _active_sessions.items():
            if current_time - session["last_activity"] > SESSION_TIMEOUT:
                stale_rooms.append(room_name)

    for room_name in stale_rooms:
        print(f"Cleaning up stale session: {room_name}")
        await end_session(room_name)

    # Also check Redis for orphaned sessions
    redis = await get_redis()
    if redis:
        keys = await redis.keys("voice_session:*")
        for key in keys:
            session_data = await json_get(key)
            if session_data:
                last_activity = session_data.get("last_activity", 0)
                if current_time - last_activity > SESSION_TIMEOUT:
                    room_name = key.split(":")[-1]
                    print(f"Cleaning up stale Redis session: {room_name}")
                    await redis.delete(key)
                    await delete_daily_room(room_name)


async def get_active_session_count() -> int:
    """Get the number of active sessions."""
    async with _session_lock:
        return len([s for s in _active_sessions.values() if s["status"] == "active"])

"""Voice onboarding routes using Daily + Pipecat"""

import os
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket
import httpx

from auth.dependencies import get_optional_user
from services.redis_client import (
    get_redis, json_get, json_set,
    get_transcription_history, get_transcription_by_key
)
from models.profile import UserProfile, VoicePreferences
from voice.category_extraction import dict_to_categories
from voice.text_fallback import (
    TextMessageRequest,
    TextMessageResponse,
    handle_text_message,
    get_text_session_status,
    end_text_session,
    get_text_session_opening
)
from voice.session_manager import (
    start_bot_for_session,
    end_session,
    get_session_status
)
from voice.websocket import websocket_endpoint
from voice.audio_websocket import audio_websocket_handler

router = APIRouter()

DAILY_API_KEY = os.getenv("DAILY_API_KEY")
DAILY_DOMAIN = os.getenv("DAILY_DOMAIN", "interestlens.daily.co")


def get_user_id(user: Optional[dict], fallback: str = "anonymous") -> str:
    """Get user ID from auth or use fallback for unauthenticated requests."""
    return user["id"] if user else fallback


@router.post("/start-session")
async def start_voice_session(user: Optional[dict] = Depends(get_optional_user)):
    """Create a Daily room for voice onboarding and start the bot"""
    user_id = get_user_id(user, "anonymous")
    user_name = user.get("name", "User") if user else "User"

    if not DAILY_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Daily API key not configured"
        )

    # Create Daily room
    async with httpx.AsyncClient() as client:
        room_response = await client.post(
            "https://api.daily.co/v1/rooms",
            headers={"Authorization": f"Bearer {DAILY_API_KEY}"},
            json={
                "properties": {
                    "exp": int(time.time()) + 3600,  # 1 hour
                    "enable_chat": False,
                    "enable_knocking": False,
                    "start_audio_off": False,
                    "start_video_off": True,
                }
            }
        )

        if room_response.status_code != 200:
            print(f"Daily room creation failed: {room_response.status_code} - {room_response.text}")

        if room_response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail="Failed to create Daily room"
            )

        room = room_response.json()

        # Create meeting token for user
        token_response = await client.post(
            "https://api.daily.co/v1/meeting-tokens",
            headers={"Authorization": f"Bearer {DAILY_API_KEY}"},
            json={
                "properties": {
                    "room_name": room["name"],
                    "user_id": user_id,
                    "user_name": user_name,
                    "enable_recording": False,
                }
            }
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail="Failed to create meeting token"
            )

        token = token_response.json()["token"]

    # Start Pipecat bot in the room
    try:
        session = await start_bot_for_session(
            room_name=room["name"],
            room_url=room["url"],
            user_id=user_id
        )
    except RuntimeError as e:
        # Max sessions reached - return 503 Service Unavailable
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )
    except Exception as e:
        print(f"Failed to start bot: {e}")
        # Bot failed but room is ready - user can still use text fallback

    return {
        "room_url": room["url"],
        "room_name": room["name"],
        "token": token,
        "expires_at": room["config"]["exp"],
        "websocket_url": f"/voice/session/{room['name']}/updates"
    }


@router.get("/session/{room_name}/status")
async def get_voice_session_status(
    room_name: str,
    user: Optional[dict] = Depends(get_optional_user)
):
    """Get the status of a voice session and current preferences"""
    status = await get_session_status(room_name)

    if not status["exists"]:
        # Check if it's a text session
        text_status = await get_text_session_status(room_name)
        if text_status["exists"]:
            return text_status

    return status


@router.post("/session/{room_name}/end")
async def end_voice_session(
    room_name: str,
    user: Optional[dict] = Depends(get_optional_user)
):
    """Manually end a voice session"""
    await end_session(room_name)
    return {
        "status": "ended",
        "room_name": room_name
    }


@router.websocket("/session/{room_name}/updates")
async def voice_session_websocket(websocket: WebSocket, room_name: str):
    """
    WebSocket endpoint for real-time voice session updates.

    Connect to receive live preference updates during voice onboarding.

    Messages sent:
    - {"type": "connected", "room_name": "...", "message": "..."}
    - {"type": "preference_update", "preferences": {...}, "topics_count": N}
    - {"type": "session_complete", "preferences": {...}}
    - {"type": "status_update", ...}
    - {"type": "error", "error": "..."}
    - {"type": "heartbeat"}

    Messages you can send:
    - {"type": "ping"} -> responds with {"type": "pong"}
    - {"type": "get_status"} -> responds with current status
    """
    await websocket_endpoint(websocket, room_name)


@router.websocket("/audio-stream/{session_id}")
async def audio_stream_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time audio streaming from Chrome extension.

    Connect to: ws://backend/voice/audio-stream/{session_id}

    This endpoint allows Chrome extensions to stream audio for voice interaction.

    Client sends:
    - {"type": "start_listening"} - Begin capturing audio
    - {"type": "audio_chunk", "data": "<base64 PCM audio>"} - Stream audio chunks
    - {"type": "stop_listening"} - Stop and process accumulated audio
    - {"type": "ping"} - Keepalive

    Server sends:
    - {"type": "connected", "session_id": "..."}
    - {"type": "listening_started"}
    - {"type": "processing", "message": "..."}
    - {"type": "transcription", "text": "...", "speaker": "user"}
    - {"type": "agent_response", "text": "...", "is_complete": bool, "preferences": {...}}
    - {"type": "error", "error": "..."}
    - {"type": "heartbeat"}
    """
    await audio_websocket_handler(websocket, session_id)


@router.post("/text-message", response_model=TextMessageResponse)
async def send_text_message(
    request: TextMessageRequest,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Send a text message for text-based onboarding fallback.

    Use this when voice fails or is unavailable.
    First message in a session will receive the opening greeting.
    """
    user_id = get_user_id(user, f"anon_{request.session_id}")
    response = await handle_text_message(
        session_id=request.session_id,
        user_id=user_id,
        message=request.message
    )
    return response


@router.get("/text-session/{session_id}/status")
async def get_text_session_status_endpoint(
    session_id: str,
    user: Optional[dict] = Depends(get_optional_user)
):
    """Get the status of a text session"""
    return await get_text_session_status(session_id)


@router.post("/text-session/{session_id}/end")
async def end_text_session_endpoint(
    session_id: str,
    user: Optional[dict] = Depends(get_optional_user)
):
    """End a text session and save preferences"""
    user_id = get_user_id(user, f"anon_{session_id}")
    preferences = await end_text_session(session_id, user_id)
    return {
        "status": "ended",
        "session_id": session_id,
        "preferences": preferences.model_dump()
    }


@router.get("/text-session/opening")
async def get_opening_message():
    """Get the opening message for a new text session"""
    opening = await get_text_session_opening()
    return {
        "message": opening
    }


@router.get("/preferences")
async def get_voice_preferences(
    session_id: Optional[str] = None,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Get user's voice onboarding preferences and extracted categories.

    Args:
        session_id: Optional session ID to get categories for a specific session

    Returns:
        Voice preferences, extracted categories, and last updated timestamp
    """
    user_id = get_user_id(user, "anonymous")
    redis = await get_redis()
    if not redis:
        return {
            "voice_onboarding_complete": False,
            "preferences": None,
            "extracted_categories": None,
            "last_updated": None
        }

    profile_data = await json_get(f"user:{user_id}")

    if not profile_data:
        return {
            "voice_onboarding_complete": False,
            "preferences": None,
            "extracted_categories": None,
            "last_updated": None
        }

    profile = UserProfile(**profile_data)

    # Get extracted categories from transcription history
    extracted_categories = None
    last_updated = None

    # Try to get from session-specific transcription
    if session_id:
        transcription_data = await get_transcription_history(user_id, session_id)
        if transcription_data:
            categories_data = transcription_data.get("extracted_categories", {})
            if categories_data.get("likes") or categories_data.get("dislikes"):
                extracted_categories = categories_data
            last_updated = transcription_data.get("updated_at")

    # If no session-specific data, try to find most recent transcription for this user
    if not extracted_categories:
        # Check for user-level transcription
        user_transcription_key = f"transcription:user:{user_id}"
        transcription_data = await get_transcription_by_key(user_transcription_key)
        if transcription_data:
            categories_data = transcription_data.get("extracted_categories", {})
            if categories_data.get("likes") or categories_data.get("dislikes"):
                extracted_categories = categories_data
            last_updated = transcription_data.get("updated_at")

    return {
        "voice_onboarding_complete": profile.voice_onboarding_complete,
        "preferences": profile.voice_preferences.model_dump() if profile.voice_preferences else None,
        "extracted_categories": extracted_categories,
        "last_updated": last_updated
    }


@router.delete("/preferences")
async def clear_voice_preferences(user: Optional[dict] = Depends(get_optional_user)):
    """Clear voice preferences and allow re-onboarding"""
    user_id = get_user_id(user, "anonymous")
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    profile_key = f"user:{user_id}"

    profile_data = await json_get(profile_key)
    if profile_data:
        profile = UserProfile(**profile_data)
        profile.voice_onboarding_complete = False
        profile.voice_preferences = None

        # Also clear topic affinities from voice
        # (keep click-based affinities)
        await json_set(profile_key, "$", profile.model_dump())

    return {
        "status": "cleared",
        "message": "Voice preferences cleared. You can set them up again anytime."
    }


@router.post("/save-preferences")
async def save_voice_preferences(
    preferences: VoicePreferences,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Save extracted voice preferences.
    Called by the Pipecat bot after conversation ends.
    """
    user_id = get_user_id(user, "anonymous")
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    profile_key = f"user:{user_id}"

    profile_data = await json_get(profile_key)
    if not profile_data:
        raise HTTPException(status_code=404, detail="User profile not found")

    profile = UserProfile(**profile_data)

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

    profile.voice_onboarding_complete = True
    profile.voice_preferences = preferences

    await json_set(profile_key, "$", profile.model_dump())

    return {
        "status": "saved",
        "topics_count": len(preferences.topics)
    }


@router.get("/transcriptions/{identifier}")
async def get_transcriptions(
    identifier: str,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Get transcription history for debugging/admin purposes.

    Args:
        identifier: Either a session_id or 'user:{user_id}' format

    Returns:
        Full transcription history with messages and extracted categories
    """
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    # Determine the key to look up
    if identifier.startswith("user:") or identifier.startswith("session:"):
        key = f"transcription:{identifier}"
    else:
        # Assume it's a session_id
        key = f"transcription:session:{identifier}"

    transcription_data = await get_transcription_by_key(key)

    if not transcription_data:
        # Try as user key
        user_id = get_user_id(user, "anonymous")
        key = f"transcription:user:{user_id}"
        transcription_data = await get_transcription_by_key(key)

    if not transcription_data:
        raise HTTPException(status_code=404, detail="Transcription not found")

    return {
        "identifier": transcription_data.get("identifier"),
        "user_id": transcription_data.get("user_id"),
        "session_id": transcription_data.get("session_id"),
        "message_count": len(transcription_data.get("messages", [])),
        "messages": transcription_data.get("messages", []),
        "extracted_categories": transcription_data.get("extracted_categories", {}),
        "final_extraction_complete": transcription_data.get("final_extraction_complete", False),
        "created_at": transcription_data.get("created_at"),
        "updated_at": transcription_data.get("updated_at")
    }

"""
Text-based conversation handler for when voice fails.
Uses the same OnboardingAgent logic but without STT/TTS.
"""

import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel

from voice.bot import OnboardingAgent
from voice.extraction import extract_final_preferences
from voice.websocket import manager as ws_manager
from models.profile import VoicePreferences


class TextMessageRequest(BaseModel):
    """Request model for text-based messages."""
    session_id: str
    message: str


class TextMessageResponse(BaseModel):
    """Response model for text-based messages."""
    response: str
    preferences_detected: Dict
    is_complete: bool
    session_id: str


# In-memory text session storage
# In production, use Redis
_text_sessions: Dict[str, OnboardingAgent] = {}
_sessions_lock = asyncio.Lock()


async def get_or_create_text_session(
    session_id: str,
    user_id: str
) -> OnboardingAgent:
    """
    Get an existing text session or create a new one.

    Args:
        session_id: Unique session identifier
        user_id: User's ID

    Returns:
        OnboardingAgent instance for the session
    """
    async with _sessions_lock:
        if session_id not in _text_sessions:
            # Create preference update callback
            async def on_update(preferences: VoicePreferences):
                await ws_manager.send_preference_update(session_id, preferences)

            # Create new agent
            agent = OnboardingAgent(
                user_id=user_id,
                room_name=session_id,  # Use session_id as room_name for consistency
                on_preferences_update=on_update
            )
            _text_sessions[session_id] = agent

        return _text_sessions[session_id]


async def handle_text_message(
    session_id: str,
    user_id: str,
    message: str
) -> TextMessageResponse:
    """
    Handle a text message from the user.

    Args:
        session_id: The session identifier
        user_id: The user's ID
        message: The user's text input

    Returns:
        TextMessageResponse with agent's response and detected preferences
    """
    agent = await get_or_create_text_session(session_id, user_id)

    # Check if this is a new session (first message)
    is_new = agent.state.turn_count == 0

    # If new session, first send the opening message context
    if is_new:
        # The opening message is already part of the agent's design
        # We'll just process the user's first message
        pass

    # Process the message
    response = await agent.process_user_message(message)

    # Get current preferences
    preferences = agent.get_current_preferences()

    # Check if session is complete
    is_complete = agent.state.is_complete

    # If complete, save preferences and cleanup
    if is_complete:
        await save_text_session_preferences(session_id, user_id, agent)
        await cleanup_text_session(session_id)

    return TextMessageResponse(
        response=response,
        preferences_detected=preferences.model_dump(),
        is_complete=is_complete,
        session_id=session_id
    )


async def save_text_session_preferences(
    session_id: str,
    user_id: str,
    agent: OnboardingAgent
):
    """Save preferences from a completed text session."""
    from voice.session_manager import save_session_preferences

    # Do final extraction from conversation history
    final_prefs = await extract_final_preferences(
        agent.state.conversation_history
    )

    # Save to user profile
    await save_session_preferences(session_id, user_id, final_prefs)


async def cleanup_text_session(session_id: str):
    """Remove a text session from memory."""
    async with _sessions_lock:
        if session_id in _text_sessions:
            del _text_sessions[session_id]


async def get_text_session_status(session_id: str) -> Dict:
    """
    Get the status of a text session.

    Args:
        session_id: The session identifier

    Returns:
        Dict with session status
    """
    async with _sessions_lock:
        if session_id in _text_sessions:
            agent = _text_sessions[session_id]
            return {
                "exists": True,
                "mode": "text",
                **agent.get_state()
            }

    return {
        "exists": False,
        "mode": "text",
        "phase": None,
        "turn_count": 0,
        "is_complete": False
    }


async def end_text_session(session_id: str, user_id: str) -> VoicePreferences:
    """
    Force end a text session and return final preferences.

    Args:
        session_id: The session identifier
        user_id: The user's ID

    Returns:
        Final VoicePreferences
    """
    async with _sessions_lock:
        if session_id not in _text_sessions:
            return VoicePreferences()

        agent = _text_sessions[session_id]

    # Force end and get final preferences
    final_prefs = await agent.force_end()

    # Save preferences
    await save_text_session_preferences(session_id, user_id, agent)

    # Cleanup
    await cleanup_text_session(session_id)

    return final_prefs


async def get_text_session_opening() -> str:
    """Get the opening message for a new text session."""
    # Same opening as voice bot
    from voice.bot import OPENING_MESSAGE
    return OPENING_MESSAGE


class TextSession:
    """
    Context manager for text sessions.
    Provides a cleaner API for managing text-based onboarding.
    """

    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.agent: Optional[OnboardingAgent] = None

    async def __aenter__(self):
        self.agent = await get_or_create_text_session(
            self.session_id,
            self.user_id
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.agent and not self.agent.state.is_complete:
            # Don't cleanup if not complete - session continues
            pass

    async def send(self, message: str) -> TextMessageResponse:
        """Send a message and get the response."""
        return await handle_text_message(
            self.session_id,
            self.user_id,
            message
        )

    async def end(self) -> VoicePreferences:
        """Force end the session."""
        return await end_text_session(self.session_id, self.user_id)

    def get_preferences(self) -> VoicePreferences:
        """Get current detected preferences."""
        if self.agent:
            return self.agent.get_current_preferences()
        return VoicePreferences()

    @property
    def is_complete(self) -> bool:
        """Check if the session is complete."""
        return self.agent.state.is_complete if self.agent else False

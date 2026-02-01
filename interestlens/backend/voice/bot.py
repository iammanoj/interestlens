"""
Pipecat OnboardingAgent - Core conversation logic for voice onboarding.
Handles opening, exploring, confirming, and closing phases of the conversation.
"""

import asyncio
import os
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

import google.generativeai as genai

from models.profile import VoicePreferences, ExtractedCategories
from voice.extraction import (
    extract_preferences_from_message,
    merge_preferences,
    preferences_to_summary,
    extract_final_preferences
)
from voice.category_extraction import (
    extract_categories_incremental,
    categories_to_dict,
    dict_to_categories
)
from services.redis_client import (
    save_transcription_message,
    get_transcription_history,
    update_extracted_categories
)

# Configure Gemini - use flash-lite for fastest response times
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
# gemini-2.0-flash-lite is optimized for low-latency, high-throughput use cases
conversation_model = genai.GenerativeModel(
    "gemini-2.0-flash-lite",
    generation_config={
        "max_output_tokens": 50,  # Limit output length for faster response
        "temperature": 0.7,
    }
)

# Limit conversation history to prevent unbounded memory growth
MAX_CONVERSATION_HISTORY = 20  # Keep last 20 messages (10 exchanges)


@dataclass
class ConversationState:
    """Tracks the state of the onboarding conversation."""
    phase: str = "opening"  # opening, exploring, confirming, closing
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    extracted_preferences: VoicePreferences = field(default_factory=VoicePreferences)
    extracted_categories: ExtractedCategories = field(default_factory=ExtractedCategories)
    turn_count: int = 0
    last_activity_time: float = 0.0
    user_id: str = ""
    room_name: str = ""
    session_id: str = ""  # Session ID for Redis storage
    is_complete: bool = False


# Conversation prompts
OPENING_MESSAGE = "Hi! What topics interest you?"

# Shorter prompt = faster LLM response
CONVERSATION_SYSTEM_PROMPT = """Onboarding assistant. Learn user preferences quickly.
Topics: {topics_summary}
History: {recent_history}
User: "{user_message}"

Reply in 8 words max. Ask one question."""


# End detection keywords
END_KEYWORDS = [
    "i'm done", "im done", "that's all", "thats all", "that is all",
    "nothing else", "no more", "stop", "i think that's it", "that's everything",
    "we're done", "were done", "all set", "good to go", "sounds good",
    "yes", "yeah", "yep", "correct", "that's right", "exactly"
]


def detect_end_intent(message: str, phase: str) -> bool:
    """Detect if user wants to end the conversation."""
    message_lower = message.lower().strip()

    # Direct end keywords
    for keyword in END_KEYWORDS:
        if keyword in message_lower:
            # In confirming phase, affirmative responses end the conversation
            if phase == "confirming" and keyword in ["yes", "yeah", "yep", "correct", "that's right", "exactly", "sounds good"]:
                return True
            # In other phases, only explicit end phrases
            elif keyword not in ["yes", "yeah", "yep", "correct", "that's right", "exactly", "sounds good"]:
                return True

    return False


class OnboardingAgent:
    """
    Voice onboarding agent that conducts conversational preference extraction.

    This class can be used both with Pipecat (as a frame processor) and
    standalone for text-based fallback.
    """

    def __init__(
        self,
        user_id: str,
        room_name: str,
        session_id: Optional[str] = None,
        on_preferences_update: Optional[Callable[[VoicePreferences], None]] = None,
        on_session_complete: Optional[Callable[[VoicePreferences], None]] = None,
        on_transcription: Optional[Callable[[str, str], None]] = None
    ):
        """
        Initialize the onboarding agent.

        Args:
            user_id: The user's ID for saving preferences
            room_name: The Daily room name for this session
            session_id: Session ID for Redis storage (defaults to room_name)
            on_preferences_update: Callback when preferences are updated (for WebSocket)
            on_session_complete: Callback when session is complete
            on_transcription: Callback for real-time transcription (text, speaker)
        """
        self.state = ConversationState(
            user_id=user_id,
            room_name=room_name,
            session_id=session_id or room_name
        )
        self.on_preferences_update = on_preferences_update
        self.on_session_complete = on_session_complete
        self.on_transcription = on_transcription
        self._lock = asyncio.Lock()

    def get_opening_message(self) -> str:
        """Get the opening message for the conversation."""
        return OPENING_MESSAGE

    async def process_user_message(self, message: str) -> str:
        """
        Process a user message and return the agent's response.

        Args:
            message: The user's transcribed speech or text input

        Returns:
            The agent's response text
        """
        async with self._lock:
            import time
            self.state.last_activity_time = time.time()
            self.state.turn_count += 1

            # Add user message to history (with limit to prevent memory growth)
            self.state.conversation_history.append({
                "role": "user",
                "content": message
            })
            # Trim history if it exceeds limit
            if len(self.state.conversation_history) > MAX_CONVERSATION_HISTORY:
                self.state.conversation_history = self.state.conversation_history[-MAX_CONVERSATION_HISTORY:]

            # Save user message to Redis (permanent storage)
            asyncio.create_task(self._save_transcription(message, "user"))

            # Notify transcription callback (user speech)
            await self._notify_transcription(message, "user")

            # Check for end intent
            if detect_end_intent(message, self.state.phase):
                if self.state.phase == "exploring":
                    # Transition to confirmation
                    self.state.phase = "confirming"
                    response = await self._generate_confirmation()
                elif self.state.phase == "confirming":
                    # User confirmed, end conversation
                    self.state.phase = "closing"
                    self.state.is_complete = True
                    response = "Done! Preferences saved."

                    # Final extraction and callback
                    if self.on_session_complete:
                        final_prefs = await extract_final_preferences(
                            self.state.conversation_history
                        )
                        await self._notify_session_complete(final_prefs)
                else:
                    response = await self._generate_response(message)
            else:
                # Run extraction and response generation IN PARALLEL for lower latency
                # Extraction runs in background while we generate the response
                extraction_task = asyncio.create_task(self._extract_and_update(message))
                response_task = asyncio.create_task(self._generate_response(message))

                # Wait for response first (user-facing latency)
                response = await response_task

                # Wait for extraction to complete (usually finishes before response)
                try:
                    await asyncio.wait_for(extraction_task, timeout=2.0)
                except asyncio.TimeoutError:
                    # Let extraction continue in background if slow
                    pass

                # Check if we should suggest wrapping up
                if self.state.turn_count >= 4 and len(self.state.extracted_preferences.topics) >= 2:
                    if self.state.phase == "exploring":
                        response += " All set?"

            # Add response to history
            self.state.conversation_history.append({
                "role": "assistant",
                "content": response
            })

            # Save assistant response to Redis (permanent storage)
            asyncio.create_task(self._save_transcription(response, "assistant"))

            # Notify transcription callback (assistant response)
            await self._notify_transcription(response, "assistant")

            return response

    async def _save_transcription(self, content: str, role: str):
        """Save a transcription message to Redis."""
        try:
            await save_transcription_message(
                user_id=self.state.user_id,
                session_id=self.state.session_id,
                role=role,
                content=content
            )
        except Exception as e:
            print(f"Transcription save error: {e}")

    async def _extract_and_update(self, message: str):
        """Extract preferences and categories from message and update state."""
        try:
            # Build context from recent history
            recent = self.state.conversation_history[-6:]  # Last 3 exchanges
            context = "\n".join(
                f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
                for m in recent
            )

            # Extract preferences (existing logic)
            extraction = await extract_preferences_from_message(message, context)

            # Merge preferences
            self.state.extracted_preferences = merge_preferences(
                self.state.extracted_preferences,
                extraction
            )

            # Extract categories incrementally (new logic)
            try:
                updated_categories = await extract_categories_incremental(
                    message=message,
                    context=context,
                    existing_categories=self.state.extracted_categories
                )
                self.state.extracted_categories = updated_categories

                # Save updated categories to Redis
                await update_extracted_categories(
                    user_id=self.state.user_id,
                    session_id=self.state.session_id,
                    categories=categories_to_dict(updated_categories)
                )
            except Exception as e:
                print(f"Category extraction error: {e}")

            # Notify via callback
            if self.on_preferences_update:
                await self._notify_preferences_update()

        except Exception as e:
            print(f"Extraction error: {e}")

    async def _notify_preferences_update(self):
        """Notify about preference updates."""
        if self.on_preferences_update:
            try:
                if asyncio.iscoroutinefunction(self.on_preferences_update):
                    await self.on_preferences_update(self.state.extracted_preferences)
                else:
                    self.on_preferences_update(self.state.extracted_preferences)
            except Exception as e:
                print(f"Preference update callback error: {e}")

    async def _notify_session_complete(self, preferences: VoicePreferences):
        """Notify about session completion."""
        if self.on_session_complete:
            try:
                if asyncio.iscoroutinefunction(self.on_session_complete):
                    await self.on_session_complete(preferences)
                else:
                    self.on_session_complete(preferences)
            except Exception as e:
                print(f"Session complete callback error: {e}")

    async def _notify_transcription(self, text: str, speaker: str):
        """Notify about real-time transcription."""
        if self.on_transcription:
            try:
                if asyncio.iscoroutinefunction(self.on_transcription):
                    await self.on_transcription(text, speaker)
                else:
                    self.on_transcription(text, speaker)
            except Exception as e:
                print(f"Transcription callback error: {e}")

    async def _generate_response(self, user_message: str) -> str:
        """Generate a conversational response using Gemini."""
        # Build topics summary
        topics_summary = "None detected yet"
        if self.state.extracted_preferences.topics:
            topics = [
                f"{t.topic} ({t.sentiment})"
                for t in self.state.extracted_preferences.topics
            ]
            topics_summary = ", ".join(topics)

        # Build recent history
        recent = self.state.conversation_history[-4:]
        recent_history = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in recent[:-1]  # Exclude current message
        )

        prompt = CONVERSATION_SYSTEM_PROMPT.format(
            topics_summary=topics_summary,
            recent_history=recent_history or "Start",
            user_message=user_message
        )

        try:
            response = await conversation_model.generate_content_async(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Response generation error: {e}")
            return "I heard you. Could you tell me more about what interests you?"

    async def _generate_confirmation(self) -> str:
        """Generate the confirmation message."""
        summary = preferences_to_summary(self.state.extracted_preferences)
        return f"Got it: {summary}. Correct?"

    def get_current_preferences(self) -> VoicePreferences:
        """Get the current extracted preferences."""
        return self.state.extracted_preferences

    def get_extracted_categories(self) -> ExtractedCategories:
        """Get the current extracted categories."""
        return self.state.extracted_categories

    def get_state(self) -> Dict:
        """Get the current conversation state for status endpoint."""
        return {
            "phase": self.state.phase,
            "turn_count": self.state.turn_count,
            "is_complete": self.state.is_complete,
            "topics_count": len(self.state.extracted_preferences.topics),
            "preferences": self.state.extracted_preferences.model_dump(),
            "extracted_categories": categories_to_dict(self.state.extracted_categories)
        }

    async def force_end(self) -> VoicePreferences:
        """Force end the conversation and return final preferences."""
        self.state.is_complete = True
        self.state.phase = "closing"

        final_prefs = await extract_final_preferences(
            self.state.conversation_history
        )

        if self.on_session_complete:
            await self._notify_session_complete(final_prefs)

        return final_prefs

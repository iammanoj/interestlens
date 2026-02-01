"""
Pipecat OnboardingAgent - Core conversation logic for voice onboarding.
Handles opening, exploring, confirming, and closing phases of the conversation.
"""

import asyncio
import os
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

import google.generativeai as genai

from models.profile import VoicePreferences
from voice.extraction import (
    extract_preferences_from_message,
    merge_preferences,
    preferences_to_summary,
    extract_final_preferences
)

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
conversation_model = genai.GenerativeModel("gemini-2.0-flash")

# Limit conversation history to prevent unbounded memory growth
MAX_CONVERSATION_HISTORY = 20  # Keep last 20 messages (10 exchanges)


@dataclass
class ConversationState:
    """Tracks the state of the onboarding conversation."""
    phase: str = "opening"  # opening, exploring, confirming, closing
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    extracted_preferences: VoicePreferences = field(default_factory=VoicePreferences)
    turn_count: int = 0
    last_activity_time: float = 0.0
    user_id: str = ""
    room_name: str = ""
    is_complete: bool = False


# Conversation prompts
OPENING_MESSAGE = (
    "Hi! I'm here to learn what content interests you. "
    "Tell me about your interests - what topics do you enjoy reading about or watching?"
)

CONVERSATION_SYSTEM_PROMPT = """You are a friendly onboarding assistant helping a user set up their content preferences.

Current conversation phase: {phase}
Topics detected so far: {topics_summary}

Your goals:
1. ACKNOWLEDGE what the user said naturally
2. ASK follow-up questions to clarify their interests
3. DETECT when they're done and transition to confirmation

Guidelines:
- Keep responses SHORT (1-2 sentences max)
- Be conversational, not robotic
- After 3-4 topics, start asking "Is there anything else?"
- If user mentions a broad topic, ask about specific aspects
- Probe for dislikes: "Any topics you'd like me to filter out?"
- Listen for intensity words: "love" vs "somewhat interested"

END DETECTION - Transition to confirmation when:
- User says: "I'm done", "that's all", "stop", "nothing else"
- User confirms there's nothing more to add
- After 5+ exchanges if coverage seems good

When transitioning to confirmation, summarize what you learned and ask if it's accurate.
When user confirms, thank them and end the conversation.

Recent conversation:
{recent_history}

User just said: "{user_message}"

Respond naturally (1-2 sentences). If transitioning phases, adjust your response accordingly."""


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
        on_preferences_update: Optional[Callable[[VoicePreferences], None]] = None,
        on_session_complete: Optional[Callable[[VoicePreferences], None]] = None,
        on_transcription: Optional[Callable[[str, str], None]] = None
    ):
        """
        Initialize the onboarding agent.

        Args:
            user_id: The user's ID for saving preferences
            room_name: The Daily room name for this session
            on_preferences_update: Callback when preferences are updated (for WebSocket)
            on_session_complete: Callback when session is complete
            on_transcription: Callback for real-time transcription (text, speaker)
        """
        self.state = ConversationState(
            user_id=user_id,
            room_name=room_name
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
                    response = "Great! Your preferences have been saved. You're all set!"

                    # Final extraction and callback
                    if self.on_session_complete:
                        final_prefs = await extract_final_preferences(
                            self.state.conversation_history
                        )
                        await self._notify_session_complete(final_prefs)
                else:
                    response = await self._generate_response(message)
            else:
                # Extract preferences from this message (async, non-blocking)
                asyncio.create_task(self._extract_and_update(message))

                # Generate conversational response
                response = await self._generate_response(message)

                # Check if we should suggest wrapping up
                if self.state.turn_count >= 5 and len(self.state.extracted_preferences.topics) >= 3:
                    if self.state.phase == "exploring":
                        response += " Is there anything else you'd like to add, or does that cover your interests?"

            # Add response to history
            self.state.conversation_history.append({
                "role": "assistant",
                "content": response
            })

            # Notify transcription callback (assistant response)
            await self._notify_transcription(response, "assistant")

            return response

    async def _extract_and_update(self, message: str):
        """Extract preferences from message and update state."""
        try:
            # Build context from recent history
            recent = self.state.conversation_history[-6:]  # Last 3 exchanges
            context = "\n".join(
                f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
                for m in recent
            )

            # Extract
            extraction = await extract_preferences_from_message(message, context)

            # Merge
            self.state.extracted_preferences = merge_preferences(
                self.state.extracted_preferences,
                extraction
            )

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
            phase=self.state.phase,
            topics_summary=topics_summary,
            recent_history=recent_history or "Start of conversation",
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
        return f"Great! Here's what I've learned: {summary} Does that sound right?"

    def get_current_preferences(self) -> VoicePreferences:
        """Get the current extracted preferences."""
        return self.state.extracted_preferences

    def get_state(self) -> Dict:
        """Get the current conversation state for status endpoint."""
        return {
            "phase": self.state.phase,
            "turn_count": self.state.turn_count,
            "is_complete": self.state.is_complete,
            "topics_count": len(self.state.extracted_preferences.topics),
            "preferences": self.state.extracted_preferences.model_dump()
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

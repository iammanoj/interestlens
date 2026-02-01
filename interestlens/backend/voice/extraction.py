"""
Preference extraction using Gemini.
Extracts content preferences from user messages during voice onboarding.
"""

import os
import json
from typing import Dict, List, Optional
import google.generativeai as genai

from models.profile import TopicPreference, ContentPreference, VoicePreferences

# Configure Gemini - use flash-lite for low latency during real-time conversation
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
# Use flash-lite for real-time extraction (faster), flash for final extraction
model = genai.GenerativeModel(
    "gemini-2.0-flash-lite",
    generation_config={
        "max_output_tokens": 200,  # Limit output for faster responses
        "temperature": 0.3,        # Lower temp = faster, more deterministic
    }
)
final_model = genai.GenerativeModel("gemini-2.0-flash")  # More thorough for final

EXTRACTION_PROMPT = """You are analyzing a conversation to extract content preferences.

Given this user message in a conversation about their content interests, extract any preferences mentioned.

User message: "{message}"

Recent conversation context:
{context}

Extract preferences and return ONLY valid JSON (no markdown, no code blocks):
{{
  "topics": [
    {{
      "topic": "topic name",
      "sentiment": "like" | "dislike" | "neutral",
      "intensity": 0.0-1.0,
      "subtopics": ["specific subtopic1", "subtopic2"],
      "avoid_subtopics": ["things to avoid within topic"]
    }}
  ],
  "content_preferences": {{
    "preferred_formats": ["articles", "videos", "podcasts", etc],
    "avoid_formats": ["format to avoid"],
    "preferred_length": "short" | "medium" | "long" | "any"
  }},
  "nothing_new": true | false
}}

Intensity guidelines:
- "love", "really enjoy", "passionate about" = 0.9-1.0
- "like", "enjoy", "interested in" = 0.7-0.8
- "somewhat interested", "kind of like" = 0.5-0.6
- "not that interested", "don't really care" = 0.3-0.4
- "don't like", "hate", "avoid" = use "dislike" sentiment with high intensity

If the message doesn't contain new preference information, set "nothing_new": true.
Only extract what is explicitly stated or strongly implied.
"""


async def extract_preferences_from_message(
    message: str,
    context: str = ""
) -> Dict:
    """
    Extract preferences from a single user message.

    Args:
        message: The user's transcribed speech
        context: Recent conversation context for reference

    Returns:
        Dict with extracted topics and content preferences
    """
    prompt = EXTRACTION_PROMPT.format(
        message=message,
        context=context or "No prior context"
    )

    try:
        print(f"[EXTRACTION] Extracting from message: '{message}'")
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        print(f"[EXTRACTION] Raw response: {text[:200]}")

        # Clean up response - remove markdown code blocks if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        result = json.loads(text)
        print(f"[EXTRACTION] Parsed result: topics={len(result.get('topics', []))}, nothing_new={result.get('nothing_new')}")
        return result

    except json.JSONDecodeError as e:
        print(f"[EXTRACTION] Failed to parse response: {e}, text was: {text[:200] if text else 'None'}")
        return {"topics": [], "content_preferences": None, "nothing_new": True}
    except Exception as e:
        print(f"[EXTRACTION] Error: {type(e).__name__}: {e}")
        return {"topics": [], "content_preferences": None, "nothing_new": True}


def merge_preferences(
    existing: VoicePreferences,
    new_extraction: Dict
) -> VoicePreferences:
    """
    Merge newly extracted preferences with existing preferences.

    Args:
        existing: Current VoicePreferences object
        new_extraction: Dict from extract_preferences_from_message

    Returns:
        Updated VoicePreferences
    """
    # Check if there are actually topics to merge (don't rely solely on nothing_new flag)
    has_topics = len(new_extraction.get("topics", [])) > 0
    if not has_topics and new_extraction.get("nothing_new", True):
        return existing

    print(f"[MERGE] Merging {len(new_extraction.get('topics', []))} new topics")

    # Merge topics
    existing_topics = {t.topic.lower(): t for t in existing.topics}

    for new_topic in new_extraction.get("topics", []):
        topic_key = new_topic.get("topic", "").lower()
        if not topic_key:
            continue

        if topic_key in existing_topics:
            # Update existing topic
            existing_t = existing_topics[topic_key]
            # Update sentiment if changed
            if new_topic.get("sentiment"):
                existing_t.sentiment = new_topic["sentiment"]
            # Update intensity (weighted average)
            if new_topic.get("intensity"):
                existing_t.intensity = (existing_t.intensity + new_topic["intensity"]) / 2
            # Merge subtopics
            for sub in new_topic.get("subtopics", []):
                if sub not in existing_t.subtopics:
                    existing_t.subtopics.append(sub)
            # Merge avoid subtopics
            for avoid in new_topic.get("avoid_subtopics", []):
                if avoid not in existing_t.avoid_subtopics:
                    existing_t.avoid_subtopics.append(avoid)
        else:
            # Add new topic
            existing.topics.append(TopicPreference(
                topic=new_topic.get("topic", "unknown"),
                sentiment=new_topic.get("sentiment", "like"),
                intensity=new_topic.get("intensity", 0.7),
                subtopics=new_topic.get("subtopics", []),
                avoid_subtopics=new_topic.get("avoid_subtopics", [])
            ))

    # Merge content preferences
    new_content = new_extraction.get("content_preferences")
    if new_content:
        if not existing.content:
            existing.content = ContentPreference()

        # Merge preferred formats
        for fmt in new_content.get("preferred_formats", []):
            if fmt not in existing.content.preferred_formats:
                existing.content.preferred_formats.append(fmt)

        # Merge avoid formats
        for fmt in new_content.get("avoid_formats", []):
            if fmt not in existing.content.avoid_formats:
                existing.content.avoid_formats.append(fmt)

        # Update length preference
        if new_content.get("preferred_length"):
            existing.content.preferred_length = new_content["preferred_length"]

    return existing


def preferences_to_summary(preferences: VoicePreferences) -> str:
    """
    Convert preferences to a human-readable summary for confirmation.

    Args:
        preferences: VoicePreferences object

    Returns:
        String summary of preferences
    """
    if not preferences.topics:
        return "I haven't detected any specific preferences yet."

    parts = []

    # Group by sentiment
    likes = [t for t in preferences.topics if t.sentiment == "like"]
    dislikes = [t for t in preferences.topics if t.sentiment == "dislike"]

    if likes:
        like_strs = []
        for t in likes:
            s = t.topic
            if t.subtopics:
                s += f" (especially {', '.join(t.subtopics[:2])})"
            like_strs.append(s)
        parts.append(f"You're interested in: {', '.join(like_strs)}")

    if dislikes:
        dislike_strs = [t.topic for t in dislikes]
        parts.append(f"You'd like to avoid: {', '.join(dislike_strs)}")

    if preferences.content and preferences.content.preferred_formats:
        parts.append(f"You prefer: {', '.join(preferences.content.preferred_formats)}")

    return ". ".join(parts) + "."


async def extract_final_preferences(
    conversation_history: List[Dict[str, str]]
) -> VoicePreferences:
    """
    Extract comprehensive preferences from the full conversation history.
    Used at the end of the session for final extraction.

    Args:
        conversation_history: List of {"role": "user"|"assistant", "content": str}

    Returns:
        Complete VoicePreferences
    """
    # Build transcript
    transcript_parts = []
    for msg in conversation_history:
        role = "User" if msg["role"] == "user" else "Assistant"
        transcript_parts.append(f"{role}: {msg['content']}")

    full_transcript = "\n".join(transcript_parts)

    final_prompt = f"""Analyze this complete conversation and extract all content preferences mentioned by the user.

Conversation transcript:
{full_transcript}

Extract ALL preferences into this JSON format (no markdown, just JSON):
{{
  "topics": [
    {{
      "topic": "topic name",
      "sentiment": "like" | "dislike" | "neutral",
      "intensity": 0.0-1.0,
      "subtopics": ["specific areas of interest"],
      "avoid_subtopics": ["specific areas to avoid"]
    }}
  ],
  "content": {{
    "preferred_formats": ["articles", "videos", etc],
    "avoid_formats": [],
    "preferred_length": "any"
  }},
  "confidence": 0.0-1.0
}}

Be thorough - capture all topics, sentiments, and specific subtopics mentioned."""

    try:
        # Use the more thorough flash model for final extraction (not latency-critical)
        response = await final_model.generate_content_async(final_prompt)
        text = response.text.strip()

        # Clean up response
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        result = json.loads(text)

        # Convert to VoicePreferences
        topics = [
            TopicPreference(
                topic=t.get("topic", ""),
                sentiment=t.get("sentiment", "like"),
                intensity=t.get("intensity", 0.7),
                subtopics=t.get("subtopics", []),
                avoid_subtopics=t.get("avoid_subtopics", [])
            )
            for t in result.get("topics", [])
            if t.get("topic")
        ]

        content = None
        if result.get("content"):
            content = ContentPreference(
                preferred_formats=result["content"].get("preferred_formats", []),
                avoid_formats=result["content"].get("avoid_formats", []),
                preferred_length=result["content"].get("preferred_length", "any")
            )

        return VoicePreferences(
            topics=topics,
            content=content,
            raw_transcript=full_transcript,
            confidence=result.get("confidence", 0.8)
        )

    except Exception as e:
        import traceback
        print(f"Final extraction error: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        print(f"Conversation had {len(conversation_history)} messages")
        # Return empty preferences but preserve the transcript for debugging
        return VoicePreferences(
            topics=[],
            content=None,
            raw_transcript=full_transcript,
            confidence=0.0
        )

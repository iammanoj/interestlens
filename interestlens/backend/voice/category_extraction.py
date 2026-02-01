"""
Category extraction from voice transcriptions using Gemini.
Extracts likes and dislikes mapped to TOPIC_CATEGORIES.
"""

import os
import asyncio
import json
import re
from typing import List, Dict, Optional, Any

import google.generativeai as genai

from models.profile import ExtractedCategory, ExtractedCategories

# Configure Gemini - use flash-lite for low-latency during real-time extraction
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
extraction_model = genai.GenerativeModel(
    "gemini-2.0-flash-lite",
    generation_config={
        "max_output_tokens": 300,  # Limit output for faster responses
        "temperature": 0.2,        # Low temp = faster, deterministic
    }
)

# API timeout in seconds - reduced for faster fail-fast
GEMINI_TIMEOUT = 10.0

# Import TOPIC_CATEGORIES from the single source of truth
from agents.pipeline import TOPIC_CATEGORIES

# Intensity keywords for sentiment analysis
STRONG_LIKE_KEYWORDS = ["love", "really like", "passionate about", "fascinated by", "obsessed with", "huge fan of"]
MODERATE_LIKE_KEYWORDS = ["like", "enjoy", "interested in", "curious about", "into"]
STRONG_DISLIKE_KEYWORDS = ["hate", "can't stand", "despise", "loathe", "really dislike"]
MODERATE_DISLIKE_KEYWORDS = ["dislike", "don't like", "not interested in", "avoid", "skip"]


def extract_json_from_response(response, default: Any = None) -> Any:
    """Safely extract JSON from a Gemini API response."""
    try:
        if response is None or not hasattr(response, 'text') or not response.text:
            return default

        text = response.text

        # Try to extract JSON from markdown code blocks
        code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        matches = re.findall(code_block_pattern, text)

        if matches:
            json_str = matches[0].strip()
        else:
            json_str = text.strip()

        return json.loads(json_str)

    except (json.JSONDecodeError, AttributeError) as e:
        print(f"[CATEGORY_EXTRACT] JSON parse error: {e}")
        return default
    except Exception as e:
        print(f"[CATEGORY_EXTRACT] Unexpected error: {e}")
        return default


async def extract_categories_incremental(
    message: str,
    context: str,
    existing_categories: Optional[ExtractedCategories] = None
) -> ExtractedCategories:
    """
    Extract categories from a single message incrementally.
    Called after each user message to update categories in real-time.

    Args:
        message: The current user message
        context: Recent conversation context (last few exchanges)
        existing_categories: Previously extracted categories to build upon

    Returns:
        Updated ExtractedCategories with any new categories found
    """
    existing_likes = []
    existing_dislikes = []
    if existing_categories:
        existing_likes = [c.category for c in existing_categories.likes]
        existing_dislikes = [c.category for c in existing_categories.dislikes]

    prompt = f"""Analyze this user message from a voice onboarding conversation to extract content preferences.

Available categories: {', '.join(TOPIC_CATEGORIES)}

Conversation context:
{context}

Current message to analyze: "{message}"

Already detected likes: {existing_likes}
Already detected dislikes: {existing_dislikes}

Extract any NEW preferences mentioned (only categories not already detected).
Look for:
- Topics they like, love, are interested in, or want to see more of
- Topics they dislike, hate, want to avoid, or aren't interested in
- The intensity of their feelings (0.0-1.0 where 1.0 is very strong)
- Specific mentions or subtopics within the category

Return JSON:
{{
  "new_likes": [
    {{
      "category": "category name from list",
      "confidence": 0.0-1.0,
      "intensity": 0.0-1.0,
      "mentions": ["specific things mentioned"],
      "subtopics": ["more specific topics"]
    }}
  ],
  "new_dislikes": [
    {{
      "category": "category name from list",
      "confidence": 0.0-1.0,
      "intensity": 0.0-1.0,
      "mentions": ["specific things mentioned"],
      "subtopics": ["more specific topics"]
    }}
  ]
}}

If no new preferences are detected, return empty arrays.
Only use categories from the provided list."""

    try:
        response = await asyncio.wait_for(
            extraction_model.generate_content_async(prompt),
            timeout=GEMINI_TIMEOUT
        )
    except asyncio.TimeoutError:
        print(f"[CATEGORY_EXTRACT] Gemini timeout after {GEMINI_TIMEOUT}s")
        return existing_categories or ExtractedCategories()
    except Exception as e:
        print(f"[CATEGORY_EXTRACT] Gemini error: {e}")
        return existing_categories or ExtractedCategories()

    result = extract_json_from_response(response, {"new_likes": [], "new_dislikes": []})

    # Build updated categories
    updated = existing_categories.model_copy() if existing_categories else ExtractedCategories()

    # Add new likes
    for like in result.get("new_likes", []):
        category = like.get("category", "")
        if category in TOPIC_CATEGORIES and category not in existing_likes:
            updated.likes.append(ExtractedCategory(
                category=category,
                confidence=float(like.get("confidence", 0.7)),
                intensity=float(like.get("intensity", 0.7)),
                mentions=like.get("mentions", []),
                subtopics=like.get("subtopics", [])
            ))

    # Add new dislikes
    for dislike in result.get("new_dislikes", []):
        category = dislike.get("category", "")
        if category in TOPIC_CATEGORIES and category not in existing_dislikes:
            updated.dislikes.append(ExtractedCategory(
                category=category,
                confidence=float(dislike.get("confidence", 0.7)),
                intensity=float(dislike.get("intensity", 0.7)),
                mentions=dislike.get("mentions", []),
                subtopics=dislike.get("subtopics", [])
            ))

    # Update overall confidence
    all_categories = updated.likes + updated.dislikes
    if all_categories:
        updated.overall_confidence = sum(c.confidence for c in all_categories) / len(all_categories)

    return updated


async def extract_categories_comprehensive(
    transcript: List[Dict[str, str]]
) -> ExtractedCategories:
    """
    Comprehensive extraction from the full conversation transcript.
    Called at session end for final, thorough analysis.

    Args:
        transcript: List of message dicts with 'role' and 'content' keys

    Returns:
        ExtractedCategories with all detected preferences
    """
    # Build full transcript text
    transcript_text = "\n".join(
        f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
        for m in transcript
    )

    prompt = f"""Analyze this complete voice onboarding conversation to extract content preferences.

Available categories: {', '.join(TOPIC_CATEGORIES)}

Full conversation transcript:
{transcript_text}

Perform a comprehensive analysis to extract ALL mentioned preferences.
For each preference, determine:
1. The category from the provided list
2. Whether it's a like or dislike
3. Confidence (0.0-1.0) - how certain are you about this preference
4. Intensity (0.0-1.0) - how strongly does the user feel about it
5. Specific mentions - exact things they mentioned
6. Subtopics - more specific areas within the category

Look for:
- Strong language: "love", "hate", "passionate", "can't stand" = high intensity
- Moderate language: "like", "enjoy", "not into", "avoid" = medium intensity
- Implied preferences from context and enthusiasm

Return JSON:
{{
  "likes": [
    {{
      "category": "category name from list",
      "confidence": 0.0-1.0,
      "intensity": 0.0-1.0,
      "mentions": ["specific things mentioned"],
      "subtopics": ["more specific topics"]
    }}
  ],
  "dislikes": [
    {{
      "category": "category name from list",
      "confidence": 0.0-1.0,
      "intensity": 0.0-1.0,
      "mentions": ["specific things mentioned"],
      "subtopics": ["more specific topics"]
    }}
  ],
  "overall_confidence": 0.0-1.0
}}

Only use categories from the provided list. Be thorough but accurate."""

    try:
        response = await asyncio.wait_for(
            extraction_model.generate_content_async(prompt),
            timeout=GEMINI_TIMEOUT
        )
    except asyncio.TimeoutError:
        print(f"[CATEGORY_EXTRACT] Comprehensive extraction timeout after {GEMINI_TIMEOUT}s")
        return ExtractedCategories()
    except Exception as e:
        print(f"[CATEGORY_EXTRACT] Comprehensive extraction error: {e}")
        return ExtractedCategories()

    result = extract_json_from_response(response, {"likes": [], "dislikes": [], "overall_confidence": 0.0})

    # Build ExtractedCategories
    likes = []
    for like in result.get("likes", []):
        category = like.get("category", "")
        if category in TOPIC_CATEGORIES:
            likes.append(ExtractedCategory(
                category=category,
                confidence=float(like.get("confidence", 0.8)),
                intensity=float(like.get("intensity", 0.8)),
                mentions=like.get("mentions", []),
                subtopics=like.get("subtopics", [])
            ))

    dislikes = []
    for dislike in result.get("dislikes", []):
        category = dislike.get("category", "")
        if category in TOPIC_CATEGORIES:
            dislikes.append(ExtractedCategory(
                category=category,
                confidence=float(dislike.get("confidence", 0.8)),
                intensity=float(dislike.get("intensity", 0.8)),
                mentions=dislike.get("mentions", []),
                subtopics=dislike.get("subtopics", [])
            ))

    return ExtractedCategories(
        likes=likes,
        dislikes=dislikes,
        overall_confidence=float(result.get("overall_confidence", 0.0))
    )


def merge_category_extractions(
    existing: ExtractedCategories,
    new: ExtractedCategories
) -> ExtractedCategories:
    """
    Merge two ExtractedCategories objects, preferring higher confidence values.

    Args:
        existing: Existing categories (e.g., from incremental extraction)
        new: New categories (e.g., from comprehensive extraction)

    Returns:
        Merged ExtractedCategories
    """
    # Create maps by category for existing
    existing_likes_map = {c.category: c for c in existing.likes}
    existing_dislikes_map = {c.category: c for c in existing.dislikes}

    # Merge likes
    merged_likes = []
    for new_like in new.likes:
        if new_like.category in existing_likes_map:
            existing_like = existing_likes_map[new_like.category]
            # Use higher confidence and intensity, merge mentions/subtopics
            merged_likes.append(ExtractedCategory(
                category=new_like.category,
                confidence=max(new_like.confidence, existing_like.confidence),
                intensity=max(new_like.intensity, existing_like.intensity),
                mentions=list(set(existing_like.mentions + new_like.mentions)),
                subtopics=list(set(existing_like.subtopics + new_like.subtopics))
            ))
            del existing_likes_map[new_like.category]
        else:
            merged_likes.append(new_like)

    # Add remaining existing likes
    merged_likes.extend(existing_likes_map.values())

    # Merge dislikes
    merged_dislikes = []
    for new_dislike in new.dislikes:
        if new_dislike.category in existing_dislikes_map:
            existing_dislike = existing_dislikes_map[new_dislike.category]
            merged_dislikes.append(ExtractedCategory(
                category=new_dislike.category,
                confidence=max(new_dislike.confidence, existing_dislike.confidence),
                intensity=max(new_dislike.intensity, existing_dislike.intensity),
                mentions=list(set(existing_dislike.mentions + new_dislike.mentions)),
                subtopics=list(set(existing_dislike.subtopics + new_dislike.subtopics))
            ))
            del existing_dislikes_map[new_dislike.category]
        else:
            merged_dislikes.append(new_dislike)

    # Add remaining existing dislikes
    merged_dislikes.extend(existing_dislikes_map.values())

    # Calculate overall confidence
    all_categories = merged_likes + merged_dislikes
    overall_confidence = 0.0
    if all_categories:
        overall_confidence = sum(c.confidence for c in all_categories) / len(all_categories)

    return ExtractedCategories(
        likes=merged_likes,
        dislikes=merged_dislikes,
        overall_confidence=max(existing.overall_confidence, new.overall_confidence, overall_confidence)
    )


def categories_to_dict(categories: ExtractedCategories) -> dict:
    """Convert ExtractedCategories to a dict for JSON storage."""
    return {
        "likes": [
            {
                "category": c.category,
                "confidence": c.confidence,
                "intensity": c.intensity,
                "mentions": c.mentions,
                "subtopics": c.subtopics
            }
            for c in categories.likes
        ],
        "dislikes": [
            {
                "category": c.category,
                "confidence": c.confidence,
                "intensity": c.intensity,
                "mentions": c.mentions,
                "subtopics": c.subtopics
            }
            for c in categories.dislikes
        ],
        "overall_confidence": categories.overall_confidence
    }


def dict_to_categories(data: dict) -> ExtractedCategories:
    """Convert a dict to ExtractedCategories."""
    likes = [
        ExtractedCategory(
            category=c.get("category", ""),
            confidence=float(c.get("confidence", 0.0)),
            intensity=float(c.get("intensity", 0.0)),
            mentions=c.get("mentions", []),
            subtopics=c.get("subtopics", [])
        )
        for c in data.get("likes", [])
    ]

    dislikes = [
        ExtractedCategory(
            category=c.get("category", ""),
            confidence=float(c.get("confidence", 0.0)),
            intensity=float(c.get("intensity", 0.0)),
            mentions=c.get("mentions", []),
            subtopics=c.get("subtopics", [])
        )
        for c in data.get("dislikes", [])
    ]

    return ExtractedCategories(
        likes=likes,
        dislikes=dislikes,
        overall_confidence=float(data.get("overall_confidence", 0.0))
    )

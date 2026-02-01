"""
4-Agent Pipeline for page analysis using Google Gemini
Agents: Extractor -> Scorer -> Explainer + Authenticity (parallel)
All calls traced with Weave
"""

import os
import asyncio
import json
import re
import math
import logging
from typing import List, Optional, Dict, Any
import weave
import google.generativeai as genai

logger = logging.getLogger(__name__)

from models.requests import PageItem, DOMOutline
from models.responses import AnalyzePageResponse, ScoredItem, ProfileSummary
from models.profile import UserProfile
from services.profile import get_user_profile
from services.redis_client import get_cached_embedding, cache_embedding
from agents.authenticity import run_authenticity_checks, is_likely_news_article

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Models
vision_model = genai.GenerativeModel("gemini-2.0-flash")
fast_model = genai.GenerativeModel("gemini-2.0-flash")
embedding_model = "models/text-embedding-004"

# API timeout in seconds
GEMINI_TIMEOUT = 30.0

# Topic categories
TOPIC_CATEGORIES = [
    "AI/ML", "programming", "cloud/infrastructure", "cybersecurity",
    "startups", "developer tools", "open source", "mobile apps",
    "finance", "business strategy", "entrepreneurship", "marketing",
    "science", "research", "space", "climate",
    "gaming", "movies/TV", "music", "sports",
    "health", "productivity", "design", "travel", "food",
    "politics", "world news", "economics", "law", "education"
]


def extract_json_from_response(response, default: Any = None) -> Any:
    """
    Safely extract JSON from a Gemini API response.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Direct JSON responses
    - Response access errors
    - Invalid JSON

    Args:
        response: The Gemini API response object
        default: Default value to return on failure

    Returns:
        Parsed JSON object or default value
    """
    try:
        # Safely get response text
        if response is None:
            logger.warning("[JSON_EXTRACT] Response is None")
            return default

        if not hasattr(response, 'text'):
            logger.warning(f"[JSON_EXTRACT] Response has no 'text' attribute: {type(response)}")
            return default

        text = response.text
        if not text:
            logger.warning("[JSON_EXTRACT] Response text is empty")
            return default

        # Try to extract JSON from markdown code blocks
        # Pattern matches ```json ... ``` or ``` ... ```
        code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        matches = re.findall(code_block_pattern, text)

        if matches:
            # Use the first code block found
            json_str = matches[0].strip()
        else:
            # Assume the entire response is JSON
            json_str = text.strip()

        # Parse JSON
        result = json.loads(json_str)
        return result

    except json.JSONDecodeError as e:
        logger.error(f"[JSON_EXTRACT] JSON parse error: {e}. Raw text: {text[:500] if text else 'N/A'}...")
        return default
    except AttributeError as e:
        logger.error(f"[JSON_EXTRACT] Attribute error accessing response: {e}")
        return default
    except Exception as e:
        logger.error(f"[JSON_EXTRACT] Unexpected error: {type(e).__name__}: {e}")
        return default


@weave.op()
async def extractor_agent(
    screenshot_base64: Optional[str],
    dom_outline: DOMOutline,
    items: List[PageItem]
) -> dict:
    """
    Agent 1: Extractor
    Analyzes page layout and classifies items as content vs nav/ads
    """
    prompt = f"""Analyze this webpage and classify each item.

Page Title: {dom_outline.title}
Headings: {', '.join(dom_outline.headings[:5])}
Number of items: {len(items)}

Items to classify:
{[{"id": i.id, "text": i.text[:100]} for i in items[:20]]}

For each item, determine:
1. Is it main content (true) or navigation/ad (false)?
2. Confidence score (0-1)

Also identify the page type: news_aggregator, video_grid, shopping, forum, or other.

Return JSON:
{{
  "page_type": "string",
  "items": [
    {{"id": "string", "is_content": boolean, "confidence": number}}
  ]
}}"""

    try:
        if screenshot_base64:
            response = await asyncio.wait_for(
                vision_model.generate_content_async([
                    {"mime_type": "image/jpeg", "data": screenshot_base64},
                    prompt
                ]),
                timeout=GEMINI_TIMEOUT
            )
        else:
            response = await asyncio.wait_for(
                fast_model.generate_content_async(prompt),
                timeout=GEMINI_TIMEOUT
            )
    except asyncio.TimeoutError:
        logger.error(f"[EXTRACTOR] Gemini API timeout after {GEMINI_TIMEOUT}s")
        response = None
    except Exception as e:
        logger.error(f"[EXTRACTOR] Gemini API error: {type(e).__name__}: {e}")
        response = None

    # Parse response with proper JSON extraction
    fallback_result = {
        "page_type": "other",
        "items": [{"id": i.id, "is_content": True, "confidence": 0.5} for i in items]
    }

    result = extract_json_from_response(response, default=fallback_result)

    # Validate result structure
    if not isinstance(result, dict) or "items" not in result:
        logger.warning(f"[EXTRACTOR] Invalid result structure, using fallback")
        result = fallback_result

    return result


@weave.op()
async def get_embedding(text: str, item_id: str) -> List[float]:
    """Get or compute embedding for text"""
    # Check cache first
    cached = await get_cached_embedding(item_id)
    if cached:
        return cached

    # Generate embedding
    result = genai.embed_content(
        model=embedding_model,
        content=text,
        task_type="retrieval_document"
    )

    embedding = result["embedding"]
    return embedding


@weave.op()
async def classify_topics(text: str) -> List[str]:
    """Classify text into topic categories"""
    prompt = f"""Classify this text into 1-3 topic categories.

Text: {text[:500]}

Available categories: {', '.join(TOPIC_CATEGORIES)}

Return only the category names as a JSON array, e.g., ["AI/ML", "startups"]"""

    try:
        response = await asyncio.wait_for(
            fast_model.generate_content_async(prompt),
            timeout=GEMINI_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.error(f"[CLASSIFY_TOPICS] Gemini API timeout after {GEMINI_TIMEOUT}s")
        return ["other"]
    except Exception as e:
        logger.error(f"[CLASSIFY_TOPICS] Gemini API error: {type(e).__name__}: {e}")
        return ["other"]

    topics = extract_json_from_response(response, default=[])

    # Validate and filter topics
    if not isinstance(topics, list):
        logger.warning(f"[CLASSIFY_TOPICS] Expected list, got {type(topics)}")
        return ["other"]

    valid_topics = [t for t in topics if isinstance(t, str) and t in TOPIC_CATEGORIES]

    if not valid_topics:
        return ["other"]

    return valid_topics


@weave.op()
async def scorer_agent(
    items: List[PageItem],
    extractor_result: dict,
    user_profile: Optional[UserProfile]
) -> List[dict]:
    """
    Agent 2: Scorer
    Calculates interest scores using embeddings and user profile.
    Uses parallel API calls for embeddings and topic classification.
    """
    # Filter to content items only
    content_ids = {
        i["id"] for i in extractor_result.get("items", [])
        if i.get("is_content", True)
    }

    content_items = [item for item in items if item.id in content_ids]

    if not content_items:
        return []

    # Parallelize embedding and topic classification calls
    async def process_item(item: PageItem) -> dict:
        # Run embedding and topic classification in parallel
        embedding, topics = await asyncio.gather(
            get_embedding(item.text, item.id),
            classify_topics(item.text)
        )

        # Calculate score
        score = calculate_score(item, embedding, topics, user_profile)

        return {
            "id": item.id,
            "score": score,
            "topics": topics,
            "embedding": embedding,
            "text": item.text
        }

    # Process all items in parallel (with implicit concurrency from asyncio.gather)
    scored_items = await asyncio.gather(
        *[process_item(item) for item in content_items],
        return_exceptions=True
    )

    # Filter out any exceptions and log them
    valid_items = []
    for i, result in enumerate(scored_items):
        if isinstance(result, Exception):
            logger.error(f"[SCORER] Error processing item {content_items[i].id}: {result}")
        else:
            valid_items.append(result)

    # Sort by score
    valid_items.sort(key=lambda x: x["score"], reverse=True)

    return valid_items[:10]  # Top 10


def calculate_score(
    item: PageItem,
    embedding: List[float],
    topics: List[str],
    profile: Optional[UserProfile]
) -> int:
    """
    Calculate interest score (0-100).

    Uses multiple signals:
    - Text embedding similarity to user's interest vector
    - Topic affinity scores (from voice + clicks)
    - Voice preferences (explicit likes/dislikes)
    - Content prominence
    """
    if not profile:
        # Limited mode: use prominence only
        prominence = 50  # Base score
        return prominence

    # Check if user has any preferences at all
    has_preferences = (
        profile.topic_affinity or
        profile.voice_preferences or
        profile.user_text_vector
    )

    if not has_preferences:
        # New user with no preferences yet
        return 50

    # Weights - voice preferences get higher weight when available
    has_voice = profile.voice_onboarding_complete and profile.voice_preferences
    if has_voice:
        W_TEXT = 0.20
        W_TOPIC = 0.35  # Topic affinity includes voice-derived affinities
        W_VOICE = 0.30  # Direct voice preference matching
        W_PROMINENCE = 0.15
    else:
        W_TEXT = 0.35
        W_TOPIC = 0.40
        W_VOICE = 0.10
        W_PROMINENCE = 0.15

    # Text similarity
    sim_text = 0.5  # Default
    if profile.user_text_vector and embedding:
        sim_text = cosine_similarity(embedding, profile.user_text_vector)

    # Topic affinity - this includes affinities from voice onboarding
    # The topic_affinity dict is populated from voice preferences in save_session_preferences
    topic_score = 0.0
    if profile.topic_affinity:
        for t in topics:
            # Check exact match and case-insensitive match
            t_lower = t.lower()
            for affinity_topic, score in profile.topic_affinity.items():
                if affinity_topic.lower() == t_lower or t_lower in affinity_topic.lower():
                    topic_score += score
                    break
        # Normalize to 0-1 range using sigmoid
        topic_score = sigmoid(topic_score / max(len(topics), 1))

    # Voice preferences boost/penalty - direct matching
    voice_modifier = 0.0
    if profile.voice_preferences and profile.voice_preferences.topics:
        topics_lower = [t.lower() for t in topics]
        for pref in profile.voice_preferences.topics:
            pref_topic_lower = pref.topic.lower()
            # Check if any item topic matches the preference topic
            for item_topic in topics_lower:
                if pref_topic_lower in item_topic or item_topic in pref_topic_lower:
                    if pref.sentiment == "like":
                        voice_modifier += pref.intensity * 0.4
                        logger.debug(f"[SCORE] Boost for liked topic '{pref.topic}' in {topics}")
                    elif pref.sentiment == "dislike":
                        voice_modifier -= pref.intensity * 0.5
                        logger.debug(f"[SCORE] Penalty for disliked topic '{pref.topic}' in {topics}")
                    break

    # Prominence (simplified - could be enhanced with position data)
    prominence = 0.5

    # Weighted sum
    raw_score = (
        W_TEXT * sim_text +
        W_TOPIC * topic_score +
        W_VOICE * (0.5 + voice_modifier) +  # 0.5 is neutral, modifier shifts up/down
        W_PROMINENCE * prominence
    )

    # Map to 0-100
    final_score = int(max(0, min(100, raw_score * 100)))

    # Log scoring for debugging
    if profile.voice_onboarding_complete:
        logger.debug(
            f"[SCORE] Item topics={topics}, "
            f"text_sim={sim_text:.2f}, topic_score={topic_score:.2f}, "
            f"voice_mod={voice_modifier:.2f}, final={final_score}"
        )

    return final_score


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def sigmoid(x: float) -> float:
    """Sigmoid function"""
    return 1 / (1 + math.exp(-x))


@weave.op()
async def explainer_agent(
    scored_items: List[dict],
    user_profile: Optional[UserProfile]
) -> List[ScoredItem]:
    """
    Agent 3: Explainer
    Generates human-readable explanations for rankings.
    Explains why items were boosted or penalized based on preferences.
    """
    explained_items = []

    top_topics = []
    liked_topics = []
    disliked_topics = []

    if user_profile:
        top_topics = [t[0] for t in user_profile.get_top_topics(3)]

        # Get voice preferences for explanation
        if user_profile.voice_preferences:
            for pref in user_profile.voice_preferences.topics:
                if pref.sentiment == "like":
                    liked_topics.append(pref.topic.lower())
                elif pref.sentiment == "dislike":
                    disliked_topics.append(pref.topic.lower())

    for item in scored_items[:5]:  # Top 5 only
        if user_profile and (top_topics or user_profile.voice_onboarding_complete):
            # Check for voice preference matches
            item_topics_lower = [t.lower() for t in item["topics"]]
            matched_likes = []
            matched_dislikes = []

            for topic in item_topics_lower:
                for liked in liked_topics:
                    if liked in topic or topic in liked:
                        matched_likes.append(liked)
                        break
                for disliked in disliked_topics:
                    if disliked in topic or topic in disliked:
                        matched_dislikes.append(disliked)
                        break

            # Generate explanation
            if matched_likes:
                why = f"Matches your interest in {', '.join(set(matched_likes))}."
            elif top_topics:
                matching = [t for t in item["topics"] if t.lower() in [tt.lower() for tt in top_topics]]
                if matching:
                    why = f"Matches your interest in {', '.join(matching)}."
                else:
                    why = f"Related to {', '.join(item['topics'][:2])}."
            else:
                why = f"Related to {', '.join(item['topics'][:2])}."

            # Add context about dislikes (lower scored items)
            if matched_dislikes:
                why += f" (Note: contains topics you're less interested in)"

            # Add voice onboarding context
            if user_profile.voice_onboarding_complete and not matched_likes and not matched_dislikes:
                why += " Based on your preferences."

        else:
            # Limited mode explanation
            why = f"Prominent content about {', '.join(item['topics'][:2])}."

        explained_items.append(ScoredItem(
            id=item["id"],
            score=item["score"],
            topics=item["topics"],
            why=why
        ))

    return explained_items


@weave.op()
async def analyze_page_pipeline(
    page_url: str,
    dom_outline: DOMOutline,
    items: List[PageItem],
    screenshot_base64: Optional[str],
    user_id: Optional[str],
    check_authenticity: bool = True
) -> AnalyzePageResponse:
    """
    Main pipeline: Extractor -> Scorer -> (Explainer + Authenticity in parallel)
    """
    # Get user profile if authenticated
    user_profile = None
    if user_id:
        user_profile = await get_user_profile(user_id)
        if user_profile:
            logger.info(
                f"[PIPELINE] User {user_id}: "
                f"voice_onboarding={user_profile.voice_onboarding_complete}, "
                f"topic_affinities={len(user_profile.topic_affinity)}, "
                f"voice_prefs={len(user_profile.voice_preferences.topics) if user_profile.voice_preferences else 0}"
            )
        else:
            logger.info(f"[PIPELINE] User {user_id}: No profile found (will use limited mode)")
    else:
        logger.info("[PIPELINE] No user_id provided (anonymous mode)")

    # Agent 1: Extract and classify items
    extractor_result = await extractor_agent(
        screenshot_base64,
        dom_outline,
        items
    )

    print("Extractor result PageType:", extractor_result.get("page_type", "other"))
    print("Number of items classified:", len(extractor_result.get("items", [])))

    # Agent 2: Score items
    scored_items = await scorer_agent(
        items,
        extractor_result,
        user_profile
    )

    # Agents 3 & 4: Run Explainer and Authenticity in parallel
    if check_authenticity:
        # Filter to news-like items for authenticity checking
        news_items = [
            item for item in scored_items[:5]
            if is_likely_news_article(item)
        ]

        # Prepare items for authenticity check (need href from original items)
        items_for_auth = []
        item_href_map = {i.id: i.href for i in items if i.href}
        for scored in news_items:
            items_for_auth.append({
                "id": scored["id"],
                "text": scored["text"],
                "topics": scored["topics"],
                "href": item_href_map.get(scored["id"], page_url),
                "url": item_href_map.get(scored["id"], page_url)
            })

        # Run explainer and authenticity in parallel
        explained_items, authenticity_results = await asyncio.gather(
            explainer_agent(scored_items, user_profile),
            run_authenticity_checks(items_for_auth, max_concurrent=3)
        )

        print("Explained items count:", len(explained_items))
        print("Authenticity results count:", len(authenticity_results))

        # Merge authenticity results into explained items
        for item in explained_items:
            if item.id in authenticity_results:
                auth = authenticity_results[item.id]
                item.authenticity_score = auth.authenticity_score
                item.authenticity_status = auth.verification_status
                item.authenticity_explanation = auth.explanation
    else:
        # Just run explainer without authenticity
        explained_items = await explainer_agent(scored_items, user_profile)

    # Build response
    profile_summary = None
    if user_profile:
        profile_summary = ProfileSummary(
            top_topics=user_profile.get_top_topics(5)
        )

    # page_type is a string, but page_topics expects a list
    page_type = extractor_result.get("page_type", "other")
    page_topics = [page_type] if isinstance(page_type, str) else page_type

    return AnalyzePageResponse(
        items=explained_items,
        page_topics=[extractor_result.get("page_type", "other")],
        profile_summary=profile_summary,
        weave_trace_url=weave.get_current_trace_url() if hasattr(weave, 'get_current_trace_url') else None
    )

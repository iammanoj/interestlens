"""
3-Agent Pipeline for page analysis using Google Gemini
Agents: Extractor -> Scorer -> Explainer
All calls traced with Weave
"""

import os
from typing import List, Optional
import weave
import google.generativeai as genai

from models.requests import PageItem, DOMOutline
from models.responses import AnalyzePageResponse, ScoredItem, ProfileSummary
from models.profile import UserProfile
from services.profile import get_user_profile
from services.redis_client import get_cached_embedding, cache_embedding

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Models
vision_model = genai.GenerativeModel("gemini-1.5-pro")
fast_model = genai.GenerativeModel("gemini-1.5-flash")
embedding_model = "models/text-embedding-004"

# Topic categories
TOPIC_CATEGORIES = [
    "AI/ML", "programming", "cloud/infrastructure", "cybersecurity",
    "startups", "developer tools", "open source", "mobile apps",
    "finance", "business strategy", "entrepreneurship", "marketing",
    "science", "research", "space", "climate",
    "gaming", "movies/TV", "music", "sports",
    "health", "productivity", "design", "travel", "food"
]


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

    if screenshot_base64:
        response = await vision_model.generate_content_async([
            {"mime_type": "image/jpeg", "data": screenshot_base64},
            prompt
        ])
    else:
        response = await fast_model.generate_content_async(prompt)

    # Parse response (simplified - add proper JSON parsing in production)
    try:
        import json
        result = json.loads(response.text)
    except:
        # Fallback: treat all items as content
        result = {
            "page_type": "other",
            "items": [{"id": i.id, "is_content": True, "confidence": 0.5} for i in items]
        }

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

    response = await fast_model.generate_content_async(prompt)

    try:
        import json
        topics = json.loads(response.text)
        return [t for t in topics if t in TOPIC_CATEGORIES]
    except:
        return ["other"]


@weave.op()
async def scorer_agent(
    items: List[PageItem],
    extractor_result: dict,
    user_profile: Optional[UserProfile]
) -> List[dict]:
    """
    Agent 2: Scorer
    Calculates interest scores using embeddings and user profile
    """
    # Filter to content items only
    content_ids = {
        i["id"] for i in extractor_result.get("items", [])
        if i.get("is_content", True)
    }

    scored_items = []

    for item in items:
        if item.id not in content_ids:
            continue

        # Get embedding
        embedding = await get_embedding(item.text, item.id)

        # Classify topics
        topics = await classify_topics(item.text)

        # Calculate score
        score = calculate_score(item, embedding, topics, user_profile)

        scored_items.append({
            "id": item.id,
            "score": score,
            "topics": topics,
            "embedding": embedding,
            "text": item.text
        })

    # Sort by score
    scored_items.sort(key=lambda x: x["score"], reverse=True)

    return scored_items[:10]  # Top 10


def calculate_score(
    item: PageItem,
    embedding: List[float],
    topics: List[str],
    profile: Optional[UserProfile]
) -> int:
    """Calculate interest score (0-100)"""
    if not profile or not profile.topic_affinity:
        # Limited mode: use prominence only
        prominence = 50  # Base score
        return prominence

    # Weights
    W_TEXT = 0.35
    W_TOPIC = 0.30
    W_VOICE = 0.20
    W_PROMINENCE = 0.15

    # Text similarity
    sim_text = 0.5  # Default
    if profile.user_text_vector and embedding:
        sim_text = cosine_similarity(embedding, profile.user_text_vector)

    # Topic affinity
    topic_score = sum(profile.topic_affinity.get(t, 0) for t in topics)
    topic_score = sigmoid(topic_score / 3)  # Normalize

    # Voice preferences boost/penalty
    voice_modifier = 0.0
    if profile.voice_preferences:
        for pref in profile.voice_preferences.topics:
            if pref.topic.lower() in [t.lower() for t in topics]:
                if pref.sentiment == "like":
                    voice_modifier += pref.intensity * 0.3
                elif pref.sentiment == "dislike":
                    voice_modifier -= pref.intensity * 0.4

    # Prominence (simplified)
    prominence = 0.5

    # Weighted sum
    raw_score = (
        W_TEXT * sim_text +
        W_TOPIC * topic_score +
        W_VOICE * (0.5 + voice_modifier) +
        W_PROMINENCE * prominence
    )

    # Map to 0-100
    return int(max(0, min(100, raw_score * 100)))


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors"""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def sigmoid(x: float) -> float:
    """Sigmoid function"""
    import math
    return 1 / (1 + math.exp(-x))


@weave.op()
async def explainer_agent(
    scored_items: List[dict],
    user_profile: Optional[UserProfile]
) -> List[ScoredItem]:
    """
    Agent 3: Explainer
    Generates human-readable explanations for rankings
    """
    explained_items = []

    top_topics = []
    if user_profile:
        top_topics = [t[0] for t in user_profile.get_top_topics(3)]

    for item in scored_items[:5]:  # Top 5 only
        if user_profile and top_topics:
            # Personalized explanation
            matching = [t for t in item["topics"] if t in top_topics]
            if matching:
                why = f"Matches your interest in {', '.join(matching)}."
            else:
                why = f"Related to {', '.join(item['topics'][:2])}."

            # Add voice preference context
            if user_profile.voice_preferences:
                for pref in user_profile.voice_preferences.topics:
                    if pref.topic.lower() in [t.lower() for t in item["topics"]]:
                        if pref.sentiment == "like":
                            why += f" You mentioned liking {pref.topic}."
                        break
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
    user_id: Optional[str]
) -> AnalyzePageResponse:
    """
    Main pipeline: Extractor -> Scorer -> Explainer
    """
    # Get user profile if authenticated
    user_profile = None
    if user_id:
        user_profile = await get_user_profile(user_id)

    # Agent 1: Extract and classify items
    extractor_result = await extractor_agent(
        screenshot_base64,
        dom_outline,
        items
    )

    # Agent 2: Score items
    scored_items = await scorer_agent(
        items,
        extractor_result,
        user_profile
    )

    # Agent 3: Generate explanations
    explained_items = await explainer_agent(
        scored_items,
        user_profile
    )

    # Build response
    profile_summary = None
    if user_profile:
        profile_summary = ProfileSummary(
            top_topics=user_profile.get_top_topics(5)
        )

    return AnalyzePageResponse(
        items=explained_items,
        page_topics=extractor_result.get("page_type", "other"),
        profile_summary=profile_summary,
        weave_trace_url=weave.get_current_trace_url() if hasattr(weave, 'get_current_trace_url') else None
    )

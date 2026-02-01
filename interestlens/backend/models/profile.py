"""User profile models"""

from typing import List, Dict, Optional
from pydantic import BaseModel


class TopicPreference(BaseModel):
    """A topic preference from voice onboarding"""
    topic: str
    sentiment: str  # "like", "dislike", "neutral"
    intensity: float  # 0.0 to 1.0
    subtopics: List[str] = []
    avoid_subtopics: List[str] = []


class ExtractedCategory(BaseModel):
    """A category extracted from voice transcription via Gemini"""
    category: str  # Must be one of TOPIC_CATEGORIES
    confidence: float  # 0.0 to 1.0 - how confident the extraction is
    intensity: float  # 0.0 to 1.0 - how strongly the user feels about it
    mentions: List[str] = []  # Specific mentions from the transcript
    subtopics: List[str] = []  # More specific topics within this category


class ExtractedCategories(BaseModel):
    """Categories extracted from voice transcription"""
    likes: List[ExtractedCategory] = []
    dislikes: List[ExtractedCategory] = []
    overall_confidence: float = 0.0  # Overall confidence in the extraction


class ContentPreference(BaseModel):
    """Content format preferences"""
    preferred_formats: List[str] = []
    avoid_formats: List[str] = []
    preferred_length: str = "any"  # "short", "medium", "long", "any"


class VoicePreferences(BaseModel):
    """Preferences extracted from voice onboarding"""
    topics: List[TopicPreference] = []
    content: Optional[ContentPreference] = None
    raw_transcript: str = ""
    confidence: float = 0.0


class UserProfile(BaseModel):
    """Complete user profile stored in Redis"""
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None

    # Embedding-based profile
    user_text_vector: List[float] = []
    user_image_vector: List[float] = []

    # Affinity scores
    topic_affinity: Dict[str, float] = {}
    domain_affinity: Dict[str, float] = {}

    # Voice onboarding
    voice_onboarding_complete: bool = False
    voice_preferences: Optional[VoicePreferences] = None

    # Stats
    interaction_count: int = 0

    def get_top_topics(self, limit: int = 5) -> List[tuple]:
        """Get top topics by affinity score"""
        sorted_topics = sorted(
            self.topic_affinity.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_topics[:limit]

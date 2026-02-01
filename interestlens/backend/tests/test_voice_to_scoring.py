"""
End-to-end tests for voice preferences affecting article scoring.
Verifies that voice onboarding preferences are properly used in content ranking.
"""

import asyncio
import sys
import os
import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from models.profile import UserProfile, VoicePreferences, TopicPreference
from models.requests import PageItem, DOMOutline
from services.redis_client import json_set, json_get, init_redis
from services.profile import get_user_profile, save_user_profile


class TestVoiceToScoring:
    """Test that voice preferences affect content scoring."""

    @pytest.mark.asyncio
    async def test_voice_preferences_affect_scoring(self):
        """
        Test that voice preferences change how content is scored.
        """
        from agents.pipeline import calculate_score
        from models.requests import PageItem

        # Create a profile with voice preferences
        profile = UserProfile(
            user_id="test_voice_scoring_user",
            voice_onboarding_complete=True,
            voice_preferences=VoicePreferences(
                topics=[
                    TopicPreference(
                        topic="AI/ML",
                        sentiment="like",
                        intensity=0.9
                    ),
                    TopicPreference(
                        topic="sports",
                        sentiment="dislike",
                        intensity=0.8
                    ),
                ],
                confidence=0.85
            ),
            topic_affinity={
                "AI/ML": 0.9,
                "machine learning": 0.8,
                "sports": -0.8,
                "football": -0.6,
            }
        )

        # Create test items
        ai_item = PageItem(
            id="ai_article_1",
            text="New developments in machine learning and AI technology",
            href="https://example.com/ai-news",
            snippet="Latest AI research breakthroughs"
        )

        sports_item = PageItem(
            id="sports_article_1",
            text="Football championship results and highlights",
            href="https://example.com/sports-news",
            snippet="Latest sports updates"
        )

        neutral_item = PageItem(
            id="neutral_article_1",
            text="Weather forecast for the week ahead",
            href="https://example.com/weather",
            snippet="Local weather predictions"
        )

        # Score items
        ai_score = calculate_score(
            ai_item,
            embedding=[0.5] * 768,  # Dummy embedding
            topics=["AI/ML", "programming"],
            profile=profile
        )

        sports_score = calculate_score(
            sports_item,
            embedding=[0.5] * 768,
            topics=["sports", "football"],
            profile=profile
        )

        neutral_score = calculate_score(
            neutral_item,
            embedding=[0.5] * 768,
            topics=["weather", "other"],
            profile=profile
        )

        print(f"\n[TEST] AI article score: {ai_score}")
        print(f"[TEST] Sports article score: {sports_score}")
        print(f"[TEST] Neutral article score: {neutral_score}")

        # AI should score higher than sports (liked vs disliked)
        assert ai_score > sports_score, (
            f"AI article ({ai_score}) should score higher than sports ({sports_score}) "
            "because user likes AI and dislikes sports"
        )

        # AI should score higher than neutral
        assert ai_score > neutral_score, (
            f"AI article ({ai_score}) should score higher than neutral ({neutral_score}) "
            "because user explicitly likes AI"
        )

    @pytest.mark.asyncio
    async def test_profile_creation_on_voice_complete(self):
        """
        Test that profiles are created if they don't exist when voice completes.
        """
        await init_redis()
        from voice.session_manager import save_session_preferences
        from services.redis_client import json_get, get_redis

        test_user_id = "voice_onboard_new_user_123"
        test_room = "voice_onboard_test_room"

        # Ensure no profile exists
        redis = await get_redis()
        if redis:
            await redis.delete(f"user:{test_user_id}")

        # Create voice preferences
        prefs = VoicePreferences(
            topics=[
                TopicPreference(
                    topic="programming",
                    sentiment="like",
                    intensity=0.85
                )
            ],
            confidence=0.8
        )

        # Save preferences (should create profile)
        await save_session_preferences(test_room, test_user_id, prefs)

        # Check profile was created
        profile_data = await json_get(f"user:{test_user_id}")
        assert profile_data is not None, "Profile should have been created"

        profile = UserProfile(**profile_data)
        assert profile.voice_onboarding_complete == True
        assert "programming" in profile.topic_affinity
        assert profile.topic_affinity["programming"] > 0

    @pytest.mark.asyncio
    async def test_no_profile_returns_default_score(self):
        """
        Test that items get a default score when no profile exists.
        """
        from agents.pipeline import calculate_score
        from models.requests import PageItem

        item = PageItem(
            id="test_item",
            text="Some test content",
            href="https://example.com",
            snippet="Test"
        )

        # No profile - should get default score
        score_no_profile = calculate_score(
            item,
            embedding=[0.5] * 768,
            topics=["technology"],
            profile=None
        )

        # Empty profile - should also get default-ish score
        empty_profile = UserProfile(user_id="empty_user")
        score_empty_profile = calculate_score(
            item,
            embedding=[0.5] * 768,
            topics=["technology"],
            profile=empty_profile
        )

        print(f"\n[TEST] Score with no profile: {score_no_profile}")
        print(f"[TEST] Score with empty profile: {score_empty_profile}")

        # Both should return reasonable default scores
        assert 40 <= score_no_profile <= 60, "Default score should be around 50"
        assert 40 <= score_empty_profile <= 60, "Empty profile score should be around 50"


class TestProfileLoading:
    """Test that profiles are loaded correctly for scoring."""

    @pytest.mark.asyncio
    async def test_profile_with_voice_preferences_loads(self):
        """Test that profiles with voice preferences load correctly."""
        await init_redis()
        """Test that profiles with voice preferences load correctly."""
        test_user_id = "profile_load_test_user"

        # Create and save a profile with voice preferences
        profile = UserProfile(
            user_id=test_user_id,
            voice_onboarding_complete=True,
            voice_preferences=VoicePreferences(
                topics=[
                    TopicPreference(
                        topic="AI/ML",
                        sentiment="like",
                        intensity=0.9
                    ),
                    TopicPreference(
                        topic="finance",
                        sentiment="like",
                        intensity=0.7
                    ),
                ],
                confidence=0.9
            ),
            topic_affinity={
                "AI/ML": 0.9,
                "finance": 0.7,
                "programming": 0.6,
            }
        )

        # Save to Redis
        await save_user_profile(profile)

        # Load it back
        loaded_profile = await get_user_profile(test_user_id)

        assert loaded_profile is not None
        assert loaded_profile.voice_onboarding_complete == True
        assert loaded_profile.voice_preferences is not None
        assert len(loaded_profile.voice_preferences.topics) == 2
        assert "AI/ML" in loaded_profile.topic_affinity

        print(f"\n[TEST] Loaded profile: voice_complete={loaded_profile.voice_onboarding_complete}")
        print(f"[TEST] Voice topics: {[t.topic for t in loaded_profile.voice_preferences.topics]}")
        print(f"[TEST] Topic affinities: {loaded_profile.topic_affinity}")


async def run_diagnostic():
    """Run a diagnostic to check current state."""
    print("\n" + "="*60)
    print("VOICE-TO-SCORING DIAGNOSTIC")
    print("="*60)

    await init_redis()

    from services.redis_client import json_get

    # Check for user profiles with voice preferences
    from services.redis_client import get_redis
    redis = await get_redis()

    if redis:
        user_keys = await redis.keys("user:*")
        print(f"\nFound {len(user_keys)} user profiles")

        for key in user_keys[:5]:  # Check first 5
            profile_data = await json_get(key)
            if profile_data:
                user_id = profile_data.get("user_id", "unknown")
                voice_complete = profile_data.get("voice_onboarding_complete", False)
                voice_prefs = profile_data.get("voice_preferences")
                topic_affinity = profile_data.get("topic_affinity", {})

                print(f"\n  Profile: {user_id}")
                print(f"    Voice onboarding complete: {voice_complete}")
                print(f"    Voice preferences: {voice_prefs is not None}")
                print(f"    Topic affinities: {len(topic_affinity)} topics")

                if voice_prefs:
                    topics = voice_prefs.get("topics", [])
                    print(f"    Voice topics: {[t.get('topic') for t in topics[:3]]}")

    # Check for transcriptions with extracted categories
    trans_keys = await redis.keys("transcription:*")
    print(f"\nFound {len(trans_keys)} transcriptions")

    for key in trans_keys[:3]:
        trans_data = await json_get(key)
        if trans_data:
            categories = trans_data.get("extracted_categories", {})
            likes = categories.get("likes", [])
            dislikes = categories.get("dislikes", [])
            print(f"\n  Transcription: {key}")
            print(f"    Likes: {[l.get('category') for l in likes]}")
            print(f"    Dislikes: {[d.get('category') for d in dislikes]}")


if __name__ == "__main__":
    # Run diagnostic
    asyncio.run(run_diagnostic())

    # Run tests
    pytest.main([__file__, "-v", "-x"])

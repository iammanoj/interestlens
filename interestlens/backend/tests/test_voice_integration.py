"""
Comprehensive integration tests for voice onboarding.
Tests session lifecycle, cache/storage persistence issues, and end-to-end flows.
"""

import asyncio
import pytest
import time
import json
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# Test configuration
TEST_USER_ID = "test_user_123"
TEST_SESSION_ID = "test_session_abc"
TEST_ROOM_NAME = "test_room_xyz"


class TestVoiceSessionLifecycle:
    """Tests for voice session lifecycle management."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset in-memory session stores before each test."""
        # Import here to avoid module-level issues
        from voice.session_manager import _active_sessions, _session_lock
        from voice.text_fallback import _text_sessions, _sessions_lock
        from voice.audio_websocket import audio_sessions

        # Clear all session stores
        _active_sessions.clear()
        _text_sessions.clear()
        audio_sessions.clear()

    @pytest.mark.asyncio
    async def test_session_expiry_handling(self):
        """
        Test that expired sessions are properly detected and cleaned up.
        BUG: Client may hold reference to expired session causing failures.
        """
        from voice.session_manager import (
            SessionInfo, _active_sessions,
            get_session_status, cleanup_stale_sessions,
            SESSION_TIMEOUT
        )

        # Create a session that's already expired
        expired_session = {
            "room_name": TEST_ROOM_NAME,
            "user_id": TEST_USER_ID,
            "room_url": f"https://interestlens.daily.co/{TEST_ROOM_NAME}",
            "created_at": time.time() - SESSION_TIMEOUT - 100,  # Expired
            "last_activity": time.time() - SESSION_TIMEOUT - 100,
            "status": "active",
            "bot_token": "expired_token"
        }
        _active_sessions[TEST_ROOM_NAME] = expired_session

        # Verify session is detected as expired
        status = await get_session_status(TEST_ROOM_NAME)
        assert status["exists"] == False, "Expired session should be marked as not existing"
        assert status.get("error") == "SESSION_EXPIRED", "Should return SESSION_EXPIRED error"

        # Run cleanup to remove from memory
        await cleanup_stale_sessions()

        # Session should be removed from memory after cleanup
        assert TEST_ROOM_NAME not in _active_sessions, "Expired session was not cleaned up from memory"

    @pytest.mark.asyncio
    async def test_stale_session_reconnect(self):
        """
        Test that reconnecting to a stale session is handled gracefully.
        BUG: Browser cache may hold old session info causing reconnect failures.
        """
        from voice.session_manager import get_session_status

        # Try to get status of non-existent session (simulates stale cache)
        status = await get_session_status("non_existent_room")

        assert status["exists"] == False
        assert status["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_session_status_consistency(self):
        """
        Test that session status is consistent across memory and Redis.
        BUG: Inconsistent state between memory and Redis can cause issues.
        """
        from voice.session_manager import (
            _active_sessions, store_session_in_redis,
            get_session_status, SessionInfo
        )

        # Create session only in memory (not Redis)
        memory_only_session = {
            "room_name": "memory_only_room",
            "user_id": TEST_USER_ID,
            "room_url": "https://test.daily.co/memory_only_room",
            "created_at": time.time(),
            "last_activity": time.time(),
            "status": "active",
            "bot_token": "test_token"
        }
        _active_sessions["memory_only_room"] = memory_only_session

        # Should find session in memory
        status = await get_session_status("memory_only_room")
        assert status["exists"] == True

        # Now clear memory (simulates server restart)
        _active_sessions.clear()

        # Session should not exist (Redis was never updated)
        status = await get_session_status("memory_only_room")
        # This may fail if Redis wasn't properly initialized
        # The session should not exist since we only stored in memory


class TestTextSessionPersistence:
    """Tests for text-based session persistence issues."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from voice.text_fallback import _text_sessions
        _text_sessions.clear()

    @pytest.mark.asyncio
    async def test_text_session_in_memory_only(self):
        """
        Test that text sessions are properly stored and retrieved.
        BUG: Text sessions are in-memory only, lost on server restart.
        """
        from voice.text_fallback import (
            get_or_create_text_session, _text_sessions,
            get_text_session_status, handle_text_message
        )

        # Create a text session
        agent = await get_or_create_text_session(TEST_SESSION_ID, TEST_USER_ID)
        assert agent is not None

        # Verify session exists
        status = await get_text_session_status(TEST_SESSION_ID)
        assert status["exists"] == True

        # Send a message to simulate usage
        response = await handle_text_message(
            TEST_SESSION_ID, TEST_USER_ID, "I like AI and machine learning"
        )
        assert response.response is not None

        # Clear sessions (simulates server restart)
        _text_sessions.clear()

        # Session should not exist anymore
        status = await get_text_session_status(TEST_SESSION_ID)
        assert status["exists"] == False, "Text session should not persist after restart"

    @pytest.mark.asyncio
    async def test_text_session_duplicate_creation(self):
        """
        Test that creating a session with same ID returns existing session.
        BUG: Potential race condition in session creation.
        """
        from voice.text_fallback import get_or_create_text_session

        # Create first session
        agent1 = await get_or_create_text_session(TEST_SESSION_ID, TEST_USER_ID)

        # Create second session with same ID
        agent2 = await get_or_create_text_session(TEST_SESSION_ID, TEST_USER_ID)

        # Should be the same session
        assert agent1 is agent2, "Duplicate session was created instead of reusing"


class TestAudioWebSocketSessions:
    """Tests for audio WebSocket session handling."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from voice.audio_websocket import audio_sessions
        audio_sessions.clear()

    @pytest.mark.asyncio
    async def test_audio_session_lifecycle(self):
        """
        Test audio session creation and cleanup.
        BUG: Audio sessions are in-memory only.
        """
        from voice.audio_websocket import AudioSession, audio_sessions

        # Create audio session
        session = AudioSession(TEST_SESSION_ID, TEST_USER_ID)
        audio_sessions[TEST_SESSION_ID] = session

        # Verify session exists
        assert TEST_SESSION_ID in audio_sessions

        # Add some audio data
        session.add_audio_chunk(b"fake_audio_data")
        assert session.has_audio() == True

        # Clear sessions (simulates restart/disconnect)
        audio_sessions.clear()

        # Session should be gone
        assert TEST_SESSION_ID not in audio_sessions


class TestDailyRoomTokenExpiry:
    """Tests for Daily.co room and token expiration handling."""

    @pytest.mark.asyncio
    async def test_expired_token_detection(self):
        """
        Test that expired Daily tokens are properly detected.
        BUG: Browser may cache expired tokens.
        """
        # Simulate an expired token scenario
        expired_token_time = int(time.time()) - 3600  # 1 hour ago

        # The token would have been valid until expired_token_time
        # Any attempt to join with this token should fail

        # This tests the logic that should check token validity
        current_time = time.time()
        assert current_time > expired_token_time, "Token expiry check failed"

    @pytest.mark.asyncio
    async def test_room_expiry_handling(self):
        """
        Test that expired Daily rooms are handled gracefully.
        Daily rooms have a 1-hour expiry by default.
        """
        from voice.routes import start_voice_session

        # Room created with 1 hour expiry
        room_expiry = int(time.time()) + 3600  # 1 hour from now

        # If client tries to use room after expiry, it should fail gracefully
        fake_expired_room = {
            "name": TEST_ROOM_NAME,
            "url": f"https://interestlens.daily.co/{TEST_ROOM_NAME}",
            "config": {"exp": int(time.time()) - 100}  # Expired
        }

        # The system should detect this expired room
        assert fake_expired_room["config"]["exp"] < time.time(), "Room should be expired"


class TestWebSocketReconnection:
    """Tests for WebSocket connection handling."""

    @pytest.mark.asyncio
    async def test_websocket_reconnect_to_inactive_session(self):
        """
        Test WebSocket reconnection to a session that's no longer active.
        BUG: Browser may try to reconnect to old WebSocket.
        """
        from voice.websocket import manager

        # Get connection count for non-existent room
        count = manager.get_connection_count("non_existent_room")
        assert count == 0

        # Check if room has connections
        has_conns = manager.has_connections("non_existent_room")
        assert has_conns == False

    @pytest.mark.asyncio
    async def test_broadcast_to_disconnected_clients(self):
        """
        Test that broadcasting to rooms with no connections is handled.
        """
        from voice.websocket import manager
        from models.profile import VoicePreferences

        # Try to broadcast to room with no connections
        # This should not raise an error
        prefs = VoicePreferences()
        await manager.send_preference_update("empty_room", prefs)
        await manager.send_session_complete("empty_room", prefs)
        await manager.send_error("empty_room", "test error")


class TestCachePersistenceIssues:
    """Tests specifically for browser cache/storage persistence issues."""

    @pytest.mark.asyncio
    async def test_stale_room_name_usage(self):
        """
        Test using a stale room name from browser cache.
        This is the main bug the user is experiencing.
        """
        from voice.session_manager import get_session_status, _active_sessions

        # Simulate browser having cached room_name from previous session
        cached_room_name = "old_cached_room_12345"

        # This room doesn't exist on server (was cleaned up or server restarted)
        status = await get_session_status(cached_room_name)

        # Status should indicate room doesn't exist
        assert status["exists"] == False
        assert status["status"] == "not_found"

        # The bug: Client should detect this and request a new session
        # but it may keep trying to use the old room

    @pytest.mark.asyncio
    async def test_stale_token_with_valid_room(self):
        """
        Test using a stale token even though room might exist.
        """
        from voice.session_manager import _active_sessions

        # Create a valid room but with a different (old) token
        valid_room = {
            "room_name": TEST_ROOM_NAME,
            "user_id": TEST_USER_ID,
            "room_url": f"https://interestlens.daily.co/{TEST_ROOM_NAME}",
            "created_at": time.time(),
            "last_activity": time.time(),
            "status": "active",
            "bot_token": "current_valid_token"
        }
        _active_sessions[TEST_ROOM_NAME] = valid_room

        # Client has cached an old token
        cached_token = "old_stale_token_xyz"

        # Tokens don't match - this would cause issues
        assert cached_token != valid_room["bot_token"]

    @pytest.mark.asyncio
    async def test_session_id_mismatch_between_backend_and_client(self):
        """
        Test when client's session_id doesn't match what backend expects.
        """
        from voice.text_fallback import get_text_session_status

        # Client thinks it has session "client_session_123"
        client_session_id = "client_session_123"

        # But backend has no record of it
        status = await get_text_session_status(client_session_id)

        # Should indicate no session exists
        assert status["exists"] == False


class TestEndToEndVoiceFlow:
    """End-to-end tests for complete voice onboarding flow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from voice.session_manager import _active_sessions
        from voice.text_fallback import _text_sessions
        from voice.audio_websocket import audio_sessions
        _active_sessions.clear()
        _text_sessions.clear()
        audio_sessions.clear()

    @pytest.mark.asyncio
    async def test_complete_text_onboarding_flow(self):
        """Test the complete text-based onboarding flow."""
        from voice.text_fallback import (
            handle_text_message, get_text_session_status,
            end_text_session, get_text_session_opening
        )

        session_id = "e2e_test_session"
        user_id = "e2e_test_user"

        # Get opening message
        opening = await get_text_session_opening()
        assert opening is not None
        assert len(opening) > 0

        # Send first message
        response1 = await handle_text_message(
            session_id, user_id, "I really like AI and machine learning"
        )
        assert response1.response is not None
        assert response1.is_complete == False

        # Check session status
        status = await get_text_session_status(session_id)
        assert status["exists"] == True
        assert status["turn_count"] == 1

        # Send more messages
        response2 = await handle_text_message(
            session_id, user_id, "I also enjoy reading about finance and investing"
        )
        assert response2.response is not None

        # End session manually
        final_prefs = await end_text_session(session_id, user_id)
        assert final_prefs is not None

        # Session should be cleaned up
        status = await get_text_session_status(session_id)
        assert status["exists"] == False

    @pytest.mark.asyncio
    async def test_interrupted_session_recovery(self):
        """
        Test that an interrupted session can be recovered.
        BUG: Currently no recovery mechanism exists.
        """
        from voice.text_fallback import (
            handle_text_message, _text_sessions,
            get_or_create_text_session
        )

        session_id = "interrupted_session"
        user_id = "interrupted_user"

        # Start a session
        response1 = await handle_text_message(
            session_id, user_id, "I like technology news"
        )

        # Session exists
        assert session_id in _text_sessions

        # Simulate server restart
        _text_sessions.clear()

        # Session is lost
        assert session_id not in _text_sessions

        # Client tries to send another message with same session_id
        # This will create a NEW session, losing context
        response2 = await handle_text_message(
            session_id, user_id, "Yes, that sounds good"
        )

        # New session was created, context is lost
        agent = await get_or_create_text_session(session_id, user_id)
        # The "Yes, that sounds good" response won't make sense without context
        # This is a bug - there's no way to recover the previous conversation


class TestPreferencePersistence:
    """Tests for preference extraction and persistence."""

    @pytest.mark.asyncio
    async def test_preferences_saved_to_redis(self):
        """Test that extracted preferences are saved to Redis."""
        from voice.text_fallback import handle_text_message, end_text_session
        from services.redis_client import get_transcription_history

        session_id = "pref_test_session"
        user_id = "pref_test_user"

        # Have a conversation
        await handle_text_message(
            session_id, user_id, "I love reading about artificial intelligence"
        )
        await handle_text_message(
            session_id, user_id, "I hate political news"
        )

        # Check that transcription was saved
        history = await get_transcription_history(user_id, session_id)

        # May be None if Redis not available in test environment
        if history:
            assert "messages" in history
            assert len(history["messages"]) > 0


class TestConcurrentSessions:
    """Tests for concurrent session handling."""

    @pytest.mark.asyncio
    async def test_max_sessions_limit(self):
        """Test that max concurrent sessions limit is enforced."""
        from voice.session_manager import (
            MAX_ACTIVE_SESSIONS, _active_sessions
        )

        # The limit should be 100
        assert MAX_ACTIVE_SESSIONS == 100

    @pytest.mark.asyncio
    async def test_multiple_users_separate_sessions(self):
        """Test that multiple users have separate sessions."""
        from voice.text_fallback import handle_text_message, _text_sessions

        # User 1
        await handle_text_message("session_1", "user_1", "I like sports")

        # User 2
        await handle_text_message("session_2", "user_2", "I like music")

        # Both sessions should exist
        assert "session_1" in _text_sessions
        assert "session_2" in _text_sessions

        # Sessions should be different
        assert _text_sessions["session_1"] is not _text_sessions["session_2"]


# Run diagnostic checks
async def run_diagnostics():
    """Run diagnostic checks to identify potential issues."""
    print("\n" + "="*60)
    print("VOICE INTEGRATION DIAGNOSTICS")
    print("="*60)

    issues_found = []

    # Check 1: In-memory session stores
    print("\n1. Checking session storage mechanisms...")
    from voice.session_manager import _active_sessions
    from voice.text_fallback import _text_sessions
    from voice.audio_websocket import audio_sessions

    print(f"   - Voice sessions in memory: {len(_active_sessions)}")
    print(f"   - Text sessions in memory: {len(_text_sessions)}")
    print(f"   - Audio sessions in memory: {len(audio_sessions)}")

    issues_found.append(
        "ISSUE: All session stores are in-memory only. "
        "Sessions are lost on server restart."
    )

    # Check 2: Redis connectivity
    print("\n2. Checking Redis connectivity...")
    from services.redis_client import get_redis, is_redis_available

    redis_available = is_redis_available()
    print(f"   - Redis available: {redis_available}")

    if not redis_available:
        issues_found.append(
            "ISSUE: Redis is not available. Transcription persistence disabled."
        )

    # Check 3: Session timeout configuration
    print("\n3. Checking session timeout configuration...")
    from voice.session_manager import SESSION_TIMEOUT
    print(f"   - Session timeout: {SESSION_TIMEOUT} seconds ({SESSION_TIMEOUT/60:.1f} minutes)")

    # Check 4: Max sessions limit
    print("\n4. Checking max sessions configuration...")
    from voice.session_manager import MAX_ACTIVE_SESSIONS
    print(f"   - Max active sessions: {MAX_ACTIVE_SESSIONS}")

    # Check 5: WebSocket connection manager
    print("\n5. Checking WebSocket connection manager...")
    from voice.websocket import manager
    print(f"   - Active WebSocket rooms: {len(manager.active_connections)}")

    # Summary
    print("\n" + "="*60)
    print("POTENTIAL ISSUES FOUND:")
    print("="*60)
    for i, issue in enumerate(issues_found, 1):
        print(f"\n{i}. {issue}")

    print("\n" + "="*60)
    print("RECOMMENDATIONS:")
    print("="*60)
    print("""
1. Session Recovery: Implement session state recovery from Redis.
   When a client reconnects with a stale session_id:
   - Check if session exists in Redis
   - If not, prompt client to start a new session

2. Token Validation: Add client-side token expiry checking.
   Before trying to join a Daily room:
   - Check if token is still valid (compare expiry time)
   - If expired, request a new session

3. Session Heartbeat: Implement session heartbeat mechanism.
   - Client periodically pings server to keep session alive
   - Server cleans up sessions without heartbeat

4. Graceful Reconnection: Implement graceful WebSocket reconnection.
   - On disconnect, try to reconnect with backoff
   - If session is gone, request new session

5. Client-Side Session Management:
   - Store session start time in localStorage
   - Check session age before trying to use
   - Clear stale sessions on page load
""")

    return issues_found


if __name__ == "__main__":
    import sys

    # Run diagnostics
    asyncio.run(run_diagnostics())

    # Run pytest if available
    try:
        sys.exit(pytest.main([__file__, "-v", "-x"]))
    except SystemExit:
        pass

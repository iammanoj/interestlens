#!/usr/bin/env python3
"""
Diagnostic script to identify voice interaction capture issues.
Run this to check system state and identify common problems.

Usage:
    python tests/diagnose_voice_issues.py [--check-redis] [--check-sessions] [--full]
"""

import asyncio
import sys
import os
import time
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()


async def check_redis_connection():
    """Check Redis connectivity and data."""
    print("\n" + "="*60)
    print("REDIS CONNECTIVITY CHECK")
    print("="*60)

    from services.redis_client import get_redis, init_redis, is_redis_available

    # Initialize if needed
    if not is_redis_available():
        print("Initializing Redis connection...")
        try:
            await init_redis()
        except Exception as e:
            print(f"ERROR: Failed to initialize Redis: {e}")
            return False

    redis = await get_redis()
    if not redis:
        print("ERROR: Redis client is None")
        return False

    try:
        # Check connectivity
        await redis.ping()
        print("SUCCESS: Redis is connected and responding")

        # Check for voice session keys
        voice_keys = await redis.keys("voice_session:*")
        print(f"\nVoice sessions in Redis: {len(voice_keys)}")
        for key in voice_keys[:5]:  # Show first 5
            print(f"  - {key}")

        # Check for transcription keys
        trans_keys = await redis.keys("transcription:*")
        print(f"\nTranscriptions in Redis: {len(trans_keys)}")
        for key in trans_keys[:5]:
            print(f"  - {key}")

        # Check for user profile keys
        user_keys = await redis.keys("user:*")
        print(f"\nUser profiles in Redis: {len(user_keys)}")
        for key in user_keys[:5]:
            print(f"  - {key}")

        return True

    except Exception as e:
        print(f"ERROR: Redis check failed: {e}")
        return False


async def check_session_state():
    """Check in-memory session state."""
    print("\n" + "="*60)
    print("SESSION STATE CHECK")
    print("="*60)

    from voice.session_manager import (
        _active_sessions, SESSION_TIMEOUT, MAX_ACTIVE_SESSIONS
    )
    from voice.text_fallback import _text_sessions
    from voice.audio_websocket import audio_sessions

    print("\nConfiguration:")
    print(f"  - Session timeout: {SESSION_TIMEOUT}s ({SESSION_TIMEOUT/60:.1f} min)")
    print(f"  - Max concurrent sessions: {MAX_ACTIVE_SESSIONS}")

    print("\nIn-Memory Sessions:")
    print(f"  - Voice sessions: {len(_active_sessions)}")
    print(f"  - Text sessions: {len(_text_sessions)}")
    print(f"  - Audio sessions: {len(audio_sessions)}")

    # Check for stale sessions
    current_time = time.time()
    stale_sessions = []

    for room_name, session in _active_sessions.items():
        last_activity = session.get("last_activity", 0)
        age = current_time - last_activity
        if age > SESSION_TIMEOUT:
            stale_sessions.append({
                "room_name": room_name,
                "age_seconds": age,
                "status": session.get("status")
            })

    if stale_sessions:
        print(f"\nWARNING: Found {len(stale_sessions)} stale voice sessions:")
        for s in stale_sessions:
            print(f"  - {s['room_name']}: {s['age_seconds']:.0f}s old, status={s['status']}")
    else:
        print("\nNo stale voice sessions found")

    # Show active sessions
    if _active_sessions:
        print("\nActive voice sessions:")
        for room_name, session in list(_active_sessions.items())[:5]:
            status = session.get("status", "unknown")
            created = session.get("created_at", 0)
            age = current_time - created
            print(f"  - {room_name}: status={status}, age={age:.0f}s")

    return True


async def check_websocket_connections():
    """Check WebSocket connection manager state."""
    print("\n" + "="*60)
    print("WEBSOCKET CONNECTIONS CHECK")
    print("="*60)

    from voice.websocket import manager

    print(f"\nActive WebSocket rooms: {len(manager.active_connections)}")
    for room_name, connections in list(manager.active_connections.items())[:5]:
        print(f"  - {room_name}: {len(connections)} connections")

    return True


async def check_daily_api():
    """Check Daily.co API connectivity."""
    print("\n" + "="*60)
    print("DAILY.CO API CHECK")
    print("="*60)

    import httpx

    DAILY_API_KEY = os.getenv("DAILY_API_KEY")
    if not DAILY_API_KEY:
        print("WARNING: DAILY_API_KEY not set")
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.daily.co/v1/rooms",
                headers={"Authorization": f"Bearer {DAILY_API_KEY}"},
                timeout=10.0
            )

            if response.status_code == 200:
                rooms = response.json()
                print(f"SUCCESS: Daily.co API is accessible")
                print(f"  - Active rooms: {len(rooms.get('data', []))}")
                return True
            else:
                print(f"ERROR: Daily.co API returned {response.status_code}")
                return False

    except Exception as e:
        print(f"ERROR: Daily.co API check failed: {e}")
        return False


async def check_environment():
    """Check required environment variables."""
    print("\n" + "="*60)
    print("ENVIRONMENT CHECK")
    print("="*60)

    required_vars = [
        "DAILY_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "REDIS_URL",
    ]

    optional_vars = [
        "DAILY_DOMAIN",
        "WANDB_API_KEY",
        "FRONTEND_URL",
    ]

    print("\nRequired variables:")
    all_present = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            masked = value[:4] + "..." + value[-4:] if len(value) > 10 else "***"
            print(f"  SUCCESS: {var} = {masked}")
        else:
            print(f"  ERROR: {var} is not set")
            all_present = False

    print("\nOptional variables:")
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            masked = value[:4] + "..." if len(value) > 4 else value
            print(f"  - {var} = {masked}")
        else:
            print(f"  - {var} is not set")

    return all_present


async def check_for_common_issues():
    """Check for common issues that cause voice capture failures."""
    print("\n" + "="*60)
    print("COMMON ISSUES CHECK")
    print("="*60)

    issues = []

    # Issue 1: In-memory session storage
    print("\n1. Session Storage Check...")
    issues.append({
        "severity": "HIGH",
        "issue": "Sessions stored in-memory only",
        "impact": "Sessions lost on server restart",
        "recommendation": "Implement Redis-backed session storage"
    })

    # Issue 2: No session validation on reconnect
    print("2. Session Validation Check...")
    issues.append({
        "severity": "HIGH",
        "issue": "No client-side session validation",
        "impact": "Browser may try to use expired sessions from cache",
        "recommendation": "Add session validation before reconnecting"
    })

    # Issue 3: Token expiry handling
    print("3. Token Expiry Check...")
    issues.append({
        "severity": "MEDIUM",
        "issue": "No client-side token expiry checking",
        "impact": "Client may send expired Daily tokens",
        "recommendation": "Check token expiry before joining rooms"
    })

    # Issue 4: WebSocket reconnection
    print("4. WebSocket Reconnection Check...")
    issues.append({
        "severity": "MEDIUM",
        "issue": "No automatic WebSocket reconnection",
        "impact": "Connection drops not recovered automatically",
        "recommendation": "Implement reconnection with exponential backoff"
    })

    print("\nIssues Found:")
    for i in issues:
        severity_color = {
            "HIGH": "!!!",
            "MEDIUM": "!!",
            "LOW": "!"
        }.get(i["severity"], "")
        print(f"\n  {severity_color} [{i['severity']}] {i['issue']}")
        print(f"     Impact: {i['impact']}")
        print(f"     Fix: {i['recommendation']}")

    return issues


async def simulate_cache_scenario():
    """Simulate the browser cache issue scenario."""
    print("\n" + "="*60)
    print("SIMULATING BROWSER CACHE SCENARIO")
    print("="*60)

    from voice.session_manager import (
        get_session_status, _active_sessions
    )
    from voice.text_fallback import (
        handle_text_message, get_text_session_status
    )

    print("""
Scenario: User opens browser with cached session data
- Browser has room_name: "cached_room_abc" in localStorage
- Browser has token: "old_token_xyz" in localStorage
- Server has been restarted (or session expired)
""")

    # Step 1: Check if cached session exists
    cached_room = "cached_room_abc"
    print(f"\n1. Client checks session status for '{cached_room}'...")
    status = await get_session_status(cached_room)
    print(f"   Result: exists={status['exists']}, status={status['status']}")

    if not status["exists"]:
        print("   ISSUE: Session doesn't exist but client may not detect this!")
        print("   The client should request a new session but might use cached data.")

    # Step 2: Simulate what happens when client uses stale session
    print(f"\n2. Client tries to send message to stale text session...")
    stale_session_id = "stale_session_123"
    status = await get_text_session_status(stale_session_id)
    print(f"   Session exists: {status['exists']}")

    if not status["exists"]:
        print("   Client would create a NEW session, losing previous context!")

        # Show what happens
        response = await handle_text_message(
            stale_session_id, "test_user", "Yes, that sounds good"
        )
        print(f"   New session created, response: '{response.response[:50]}...'")
        print("   BUG: Response won't make sense without previous context!")

    # Step 3: Recommended fix
    print("\n3. RECOMMENDED CLIENT-SIDE FIX:")
    print("""
   async function checkAndRecoverSession(cachedSessionId) {
     const status = await fetch(`/voice/session/${cachedSessionId}/status`);
     const data = await status.json();

     if (!data.exists) {
       // Clear cached data
       localStorage.removeItem('voice_session_id');
       localStorage.removeItem('voice_room_token');

       // Request new session
       return await startNewVoiceSession();
     }

     return cachedSessionId;
   }
""")


async def run_full_diagnostics():
    """Run all diagnostic checks."""
    print("\n" + "#"*70)
    print("INTERESTLENS VOICE INTEGRATION DIAGNOSTICS")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("#"*70)

    results = {}

    # Environment check
    results["environment"] = await check_environment()

    # Redis check
    results["redis"] = await check_redis_connection()

    # Session state check
    results["sessions"] = await check_session_state()

    # WebSocket check
    results["websockets"] = await check_websocket_connections()

    # Daily.co API check
    results["daily_api"] = await check_daily_api()

    # Common issues check
    issues = await check_for_common_issues()
    results["issues_count"] = len(issues)

    # Cache scenario simulation
    await simulate_cache_scenario()

    # Summary
    print("\n" + "#"*70)
    print("DIAGNOSTIC SUMMARY")
    print("#"*70)

    print("\nResults:")
    for check, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  - {check}: {status}")

    # Overall recommendation
    print("\n" + "="*60)
    print("RECOMMENDED FIXES FOR CACHE/STORAGE ISSUES")
    print("="*60)
    print("""
1. CLIENT-SIDE: Add session validation on page load
   - Before using cached session data, validate with backend
   - If session invalid/expired, clear cache and start fresh

2. CLIENT-SIDE: Add token expiry checking
   - Store token expiry time alongside token
   - Check expiry before attempting to join Daily room

3. CLIENT-SIDE: Add automatic WebSocket reconnection
   - On disconnect, try to reconnect with exponential backoff
   - After max retries, prompt user to start new session

4. SERVER-SIDE: Add session recovery from Redis
   - Store full session state in Redis, not just in-memory
   - On reconnect, restore session from Redis if available

5. SERVER-SIDE: Return clear error codes
   - When session doesn't exist: {"error": "SESSION_NOT_FOUND"}
   - When token expired: {"error": "TOKEN_EXPIRED"}
   - Client can handle these specifically
""")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose voice interaction capture issues"
    )
    parser.add_argument(
        "--check-redis", action="store_true",
        help="Only check Redis connectivity"
    )
    parser.add_argument(
        "--check-sessions", action="store_true",
        help="Only check session state"
    )
    parser.add_argument(
        "--check-env", action="store_true",
        help="Only check environment variables"
    )
    parser.add_argument(
        "--simulate", action="store_true",
        help="Only run cache scenario simulation"
    )
    parser.add_argument(
        "--full", action="store_true", default=True,
        help="Run full diagnostics (default)"
    )

    args = parser.parse_args()

    if args.check_redis:
        asyncio.run(check_redis_connection())
    elif args.check_sessions:
        asyncio.run(check_session_state())
    elif args.check_env:
        asyncio.run(check_environment())
    elif args.simulate:
        asyncio.run(simulate_cache_scenario())
    else:
        asyncio.run(run_full_diagnostics())


if __name__ == "__main__":
    main()

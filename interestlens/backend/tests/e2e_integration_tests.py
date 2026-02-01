#!/usr/bin/env python3
"""
End-to-End Integration Tests for InterestLens Chrome Extension API

Tests all API endpoints, payloads, error handling, and fallback scenarios
that the Chrome Extension relies on.

Run: python tests/e2e_integration_tests.py
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass, field

BASE_URL = "http://localhost:8001"

@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float
    details: str = ""
    error: str = ""

@dataclass
class TestSuite:
    name: str
    results: List[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)


class IntegrationTestRunner:
    def __init__(self):
        self.suites: List[TestSuite] = []
        self.session: aiohttp.ClientSession = None

    async def setup(self):
        self.session = aiohttp.ClientSession()

    async def teardown(self):
        if self.session:
            await self.session.close()

    async def run_test(self, name: str, coro) -> TestResult:
        start = time.time()
        try:
            result = await coro
            duration = (time.time() - start) * 1000
            if isinstance(result, tuple):
                passed, details = result
            else:
                passed, details = result, ""
            return TestResult(name=name, passed=passed, duration_ms=duration, details=details)
        except Exception as e:
            duration = (time.time() - start) * 1000
            return TestResult(name=name, passed=False, duration_ms=duration, error=str(e))

    # ==================== HEALTH CHECK TESTS ====================

    async def test_health_check(self) -> Tuple[bool, str]:
        async with self.session.get(f"{BASE_URL}/health") as resp:
            data = await resp.json()
            passed = resp.status == 200 and data.get("status") == "healthy"
            return passed, f"Status: {data.get('status')}"

    async def test_health_check_method_not_allowed(self) -> Tuple[bool, str]:
        async with self.session.post(f"{BASE_URL}/health") as resp:
            # Should return 405 Method Not Allowed
            passed = resp.status == 405
            return passed, f"Status code: {resp.status}"

    # ==================== ANALYZE PAGE TESTS ====================

    async def test_analyze_page_basic(self) -> Tuple[bool, str]:
        payload = {
            "page_url": "https://news.ycombinator.com/",
            "dom_outline": {
                "title": "Hacker News",
                "headings": ["Hacker News"],
                "main_text_excerpt": "Tech news"
            },
            "items": [
                {"id": "1", "text": "AI startup raises $100M", "bbox": [0, 0, 100, 50]},
                {"id": "2", "text": "New programming language released", "bbox": [0, 60, 100, 50]}
            ]
        }
        async with self.session.post(f"{BASE_URL}/analyze_page", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and "items" in data and len(data["items"]) > 0
            return passed, f"Items returned: {len(data.get('items', []))}"

    async def test_analyze_page_empty_items(self) -> Tuple[bool, str]:
        payload = {
            "page_url": "https://example.com/",
            "dom_outline": {"title": "Test", "headings": [], "main_text_excerpt": ""},
            "items": []
        }
        async with self.session.post(f"{BASE_URL}/analyze_page", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and data.get("items") == []
            return passed, f"Empty items handled correctly"

    async def test_analyze_page_missing_fields(self) -> Tuple[bool, str]:
        payload = {"page_url": "https://example.com/"}  # Missing required fields
        async with self.session.post(f"{BASE_URL}/analyze_page", json=payload) as resp:
            passed = resp.status == 422  # Validation error
            return passed, f"Status code: {resp.status}"

    async def test_analyze_page_invalid_bbox(self) -> Tuple[bool, str]:
        payload = {
            "page_url": "https://example.com/",
            "dom_outline": {"title": "Test", "headings": [], "main_text_excerpt": ""},
            "items": [{"id": "1", "text": "Test", "bbox": [0.5, 1.5, 100.7, 50.3]}]  # Float bbox
        }
        async with self.session.post(f"{BASE_URL}/analyze_page", json=payload) as resp:
            passed = resp.status == 200  # Should accept float bbox
            return passed, f"Float bbox accepted: {resp.status == 200}"

    async def test_analyze_page_large_payload(self) -> Tuple[bool, str]:
        items = [{"id": f"item_{i}", "text": f"Item {i} " * 50, "bbox": [0, i*30, 500, 25]}
                 for i in range(50)]
        payload = {
            "page_url": "https://example.com/",
            "dom_outline": {"title": "Test", "headings": [], "main_text_excerpt": ""},
            "items": items
        }
        async with self.session.post(f"{BASE_URL}/analyze_page", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200
            return passed, f"Processed {len(items)} items"

    # ==================== EVENT LOGGING TESTS ====================
    # Note: /event requires authentication. These tests verify both auth behavior
    # and functionality with a dev token.

    async def _get_dev_token(self) -> str:
        """Get a dev token for authenticated tests"""
        payload = {"user_id": "test_dev_user", "email": "test@example.com", "name": "Test User"}
        async with self.session.post(f"{BASE_URL}/auth/dev-token", json=payload) as resp:
            data = await resp.json()
            return data.get("access_token", "")

    async def test_event_requires_auth(self) -> Tuple[bool, str]:
        """Events require authentication - should return 401 without token"""
        payload = {
            "event": "click",
            "item_id": "test_item_1",
            "page_url": "https://example.com/",
            "timestamp": int(time.time() * 1000),
            "item_data": {"text": "Test item", "topics": ["AI"]}
        }
        async with self.session.post(f"{BASE_URL}/event", json=payload) as resp:
            passed = resp.status == 401  # Expected: auth required
            return passed, f"Returns 401 without auth (expected)"

    async def test_event_click_with_auth(self) -> Tuple[bool, str]:
        token = await self._get_dev_token()
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "event": "click",
            "item_id": "test_item_1",
            "page_url": "https://example.com/",
            "timestamp": int(time.time() * 1000),
            "item_data": {"text": "Test item", "topics": ["AI"]}
        }
        async with self.session.post(f"{BASE_URL}/event", json=payload, headers=headers) as resp:
            passed = resp.status == 200
            return passed, f"Click event logged with auth"

    async def test_event_thumbs_up_with_auth(self) -> Tuple[bool, str]:
        token = await self._get_dev_token()
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "event": "thumbs_up",
            "item_id": "test_item_2",
            "page_url": "https://example.com/",
            "timestamp": int(time.time() * 1000),
            "item_data": {"text": "Good item", "topics": ["programming"]}
        }
        async with self.session.post(f"{BASE_URL}/event", json=payload, headers=headers) as resp:
            passed = resp.status == 200
            return passed, f"Thumbs up logged with auth"

    async def test_event_thumbs_down_with_auth(self) -> Tuple[bool, str]:
        token = await self._get_dev_token()
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "event": "thumbs_down",
            "item_id": "test_item_3",
            "page_url": "https://example.com/",
            "timestamp": int(time.time() * 1000),
            "item_data": {"text": "Bad item", "topics": ["crypto"]}
        }
        async with self.session.post(f"{BASE_URL}/event", json=payload, headers=headers) as resp:
            passed = resp.status == 200
            return passed, f"Thumbs down logged with auth"

    async def test_event_missing_fields_with_auth(self) -> Tuple[bool, str]:
        token = await self._get_dev_token()
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"event": "click"}  # Missing required fields
        async with self.session.post(f"{BASE_URL}/event", json=payload, headers=headers) as resp:
            passed = resp.status == 422
            return passed, f"Validation error returned: {resp.status}"

    # ==================== ACTIVITY TRACKING TESTS ====================

    async def test_activity_track_page_visit(self) -> Tuple[bool, str]:
        payload = {
            "activities": [{
                "type": "page_visit",
                "timestamp": int(time.time() * 1000),
                "data": {
                    "url": "https://example.com/article",
                    "domain": "example.com",
                    "title": "Test Article",
                    "timeSpent": 5000,
                    "scrollDepth": 75,
                    "categories": ["technology"]
                },
                "sourceUrl": "https://example.com/",
                "sourceDomain": "example.com"
            }],
            "client_timestamp": int(time.time() * 1000)
        }
        async with self.session.post(f"{BASE_URL}/activity/track", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and data.get("status") == "ok"
            return passed, f"Activities processed: {data.get('activities_processed', 0)}"

    async def test_activity_track_click(self) -> Tuple[bool, str]:
        payload = {
            "activities": [{
                "type": "click",
                "timestamp": int(time.time() * 1000),
                "data": {
                    "url": "https://example.com/link",
                    "text": "Click me",
                    "isArticleLink": True
                },
                "sourceUrl": "https://example.com/",
                "sourceDomain": "example.com"
            }],
            "client_timestamp": int(time.time() * 1000)
        }
        async with self.session.post(f"{BASE_URL}/activity/track", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200
            return passed, f"Click activity tracked"

    async def test_activity_track_missing_timestamp(self) -> Tuple[bool, str]:
        """Test fallback when activity timestamp is missing"""
        payload = {
            "activities": [{
                "type": "click",
                "data": {"url": "https://example.com/"},
                "sourceUrl": "https://example.com/",
                "sourceDomain": "example.com"
                # timestamp is missing - should use default
            }],
            "client_timestamp": int(time.time() * 1000)
        }
        async with self.session.post(f"{BASE_URL}/activity/track", json=payload) as resp:
            passed = resp.status == 200  # Should succeed with fallback
            return passed, f"Missing timestamp handled with fallback"

    async def test_activity_track_empty_activities(self) -> Tuple[bool, str]:
        payload = {
            "activities": [],
            "client_timestamp": int(time.time() * 1000)
        }
        async with self.session.post(f"{BASE_URL}/activity/track", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and data.get("activities_processed") == 0
            return passed, f"Empty activities handled"

    async def test_activity_track_batch(self) -> Tuple[bool, str]:
        """Test batch activity tracking"""
        activities = [
            {
                "type": "page_visit",
                "timestamp": int(time.time() * 1000) - i * 1000,
                "data": {"url": f"https://example.com/page{i}", "domain": "example.com"},
                "sourceUrl": "https://example.com/",
                "sourceDomain": "example.com"
            }
            for i in range(10)
        ]
        payload = {"activities": activities, "client_timestamp": int(time.time() * 1000)}
        async with self.session.post(f"{BASE_URL}/activity/track", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and data.get("activities_processed") == 10
            return passed, f"Batch of 10 activities processed"

    # ==================== VOICE ONBOARDING TESTS ====================

    async def test_voice_start_session(self) -> Tuple[bool, str]:
        payload = {"user_id": "test_user_e2e"}
        async with self.session.post(f"{BASE_URL}/voice/start-session", json=payload) as resp:
            data = await resp.json()
            passed = (resp.status == 200 and
                     "room_url" in data and
                     "token" in data and
                     "websocket_url" in data)
            return passed, f"Room created: {data.get('room_name', 'N/A')[:20]}"

    async def test_voice_text_message_first(self) -> Tuple[bool, str]:
        session_id = f"e2e_test_{int(time.time())}"
        payload = {"session_id": session_id, "message": "Hello"}
        async with self.session.post(f"{BASE_URL}/voice/text-message", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and "response" in data
            return passed, f"Bot response: {data.get('response', 'N/A')[:50]}"

    async def test_voice_text_message_with_interests(self) -> Tuple[bool, str]:
        session_id = f"e2e_test_{int(time.time())}"
        # First message
        await self.session.post(f"{BASE_URL}/voice/text-message",
                               json={"session_id": session_id, "message": "Hi"})
        # Second message with interests
        payload = {"session_id": session_id, "message": "I love AI and technology"}
        async with self.session.post(f"{BASE_URL}/voice/text-message", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200
            topics = [t.get("topic") for t in data.get("preferences", {}).get("topics", [])]
            return passed, f"Topics detected: {topics}"

    async def test_voice_text_message_end_intent(self) -> Tuple[bool, str]:
        session_id = f"e2e_end_{int(time.time())}"
        # Setup conversation
        await self.session.post(f"{BASE_URL}/voice/text-message",
                               json={"session_id": session_id, "message": "I like programming"})
        # End intent
        payload = {"session_id": session_id, "message": "that's all"}
        async with self.session.post(f"{BASE_URL}/voice/text-message", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and "Correct?" in data.get("response", "")
            return passed, f"End detected, confirmation requested"

    async def test_voice_session_status(self) -> Tuple[bool, str]:
        # Create a session first
        create_resp = await self.session.post(f"{BASE_URL}/voice/start-session",
                                              json={"user_id": "status_test"})
        create_data = await create_resp.json()
        room_name = create_data.get("room_name")

        async with self.session.get(f"{BASE_URL}/voice/session/{room_name}/status") as resp:
            data = await resp.json()
            passed = resp.status == 200 and data.get("exists") == True
            return passed, f"Session status: {data.get('status', 'N/A')}"

    async def test_voice_session_status_not_found(self) -> Tuple[bool, str]:
        async with self.session.get(f"{BASE_URL}/voice/session/nonexistent_room/status") as resp:
            data = await resp.json()
            passed = resp.status == 200 and data.get("exists") == False
            return passed, f"Non-existent session handled"

    async def test_voice_get_opening_message(self) -> Tuple[bool, str]:
        async with self.session.get(f"{BASE_URL}/voice/text-session/opening") as resp:
            data = await resp.json()
            passed = resp.status == 200 and "message" in data
            return passed, f"Opening: {data.get('message', 'N/A')[:30]}"

    # ==================== PREFERENCES TESTS ====================

    async def test_preferences_get(self) -> Tuple[bool, str]:
        async with self.session.get(f"{BASE_URL}/voice/preferences") as resp:
            data = await resp.json()
            passed = resp.status == 200 and "voice_onboarding_complete" in data
            return passed, f"Onboarding complete: {data.get('voice_onboarding_complete')}"

    async def test_preferences_save(self) -> Tuple[bool, str]:
        payload = {
            "preferences": {
                "topics": [
                    {"topic": "AI", "sentiment": "like", "intensity": 0.9, "subtopics": [], "avoid_subtopics": []},
                    {"topic": "sports", "sentiment": "dislike", "intensity": 0.7, "subtopics": [], "avoid_subtopics": []}
                ],
                "content": {"preferred_formats": [], "avoid_formats": [], "preferred_length": "any"},
                "raw_transcript": "Test transcript",
                "confidence": 0.8
            },
            "category_likes": ["technology"],
            "category_dislikes": ["politics"]
        }
        async with self.session.post(f"{BASE_URL}/voice/save-preferences", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and data.get("status") == "saved"
            return passed, f"Preferences saved"

    async def test_preferences_debug_profile(self) -> Tuple[bool, str]:
        async with self.session.get(f"{BASE_URL}/voice/debug/user-profile") as resp:
            data = await resp.json()
            passed = resp.status == 200 and "user_id" in data
            return passed, f"User ID: {data.get('user_id', 'N/A')}"

    # ==================== AUTHENTICATION TESTS ====================

    async def test_auth_google_redirect(self) -> Tuple[bool, str]:
        async with self.session.get(f"{BASE_URL}/auth/google", allow_redirects=False) as resp:
            passed = resp.status in [302, 307]  # Redirect to Google
            return passed, f"Redirects to Google OAuth"

    async def test_auth_me_unauthenticated(self) -> Tuple[bool, str]:
        async with self.session.get(f"{BASE_URL}/auth/me") as resp:
            passed = resp.status == 401
            return passed, f"Returns 401 for unauthenticated"

    async def test_auth_dev_token(self) -> Tuple[bool, str]:
        payload = {"user_id": "test_dev_user", "email": "test@example.com", "name": "Test User"}
        async with self.session.post(f"{BASE_URL}/auth/dev-token", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and "access_token" in data
            return passed, f"Dev token generated"

    # ==================== ERROR HANDLING TESTS ====================

    async def test_404_endpoint(self) -> Tuple[bool, str]:
        async with self.session.get(f"{BASE_URL}/nonexistent/endpoint") as resp:
            passed = resp.status == 404
            return passed, f"404 returned for unknown endpoint"

    async def test_invalid_json(self) -> Tuple[bool, str]:
        async with self.session.post(
            f"{BASE_URL}/analyze_page",
            data="not json",
            headers={"Content-Type": "application/json"}
        ) as resp:
            passed = resp.status == 422
            return passed, f"Invalid JSON handled"

    async def test_cors_headers(self) -> Tuple[bool, str]:
        """CORS headers should be present on responses"""
        # Must send Origin header to trigger CORS middleware
        headers = {"Origin": "chrome-extension://test-extension-id"}
        async with self.session.get(f"{BASE_URL}/health", headers=headers) as resp:
            cors_header = resp.headers.get("access-control-allow-origin", "")
            passed = cors_header == "*"
            return passed, f"CORS header: {cors_header}"

    # ==================== FALLBACK SCENARIO TESTS ====================

    async def test_analyze_page_without_auth(self) -> Tuple[bool, str]:
        """Extension should work without authentication (limited mode)"""
        payload = {
            "page_url": "https://example.com/",
            "dom_outline": {"title": "Test", "headings": [], "main_text_excerpt": ""},
            "items": [{"id": "1", "text": "Test item", "bbox": [0, 0, 100, 50]}]
        }
        async with self.session.post(f"{BASE_URL}/analyze_page", json=payload) as resp:
            passed = resp.status == 200
            return passed, f"Works without auth (limited mode)"

    async def test_voice_text_fallback_when_daily_unavailable(self) -> Tuple[bool, str]:
        """Text-based onboarding should work as fallback"""
        session_id = f"fallback_test_{int(time.time())}"
        payload = {"session_id": session_id, "message": "I like technology"}
        async with self.session.post(f"{BASE_URL}/voice/text-message", json=payload) as resp:
            data = await resp.json()
            passed = resp.status == 200 and "response" in data
            return passed, f"Text fallback works"

    async def test_activity_tracking_graceful_degradation(self) -> Tuple[bool, str]:
        """Activity tracking should not fail even with minimal data"""
        payload = {
            "activities": [{"type": "click", "data": {}, "sourceUrl": "", "sourceDomain": ""}],
            "client_timestamp": int(time.time() * 1000)
        }
        async with self.session.post(f"{BASE_URL}/activity/track", json=payload) as resp:
            passed = resp.status == 200
            return passed, f"Handles minimal data gracefully"

    # ==================== RUN ALL TESTS ====================

    async def run_all_tests(self):
        await self.setup()

        print("=" * 70)
        print("InterestLens E2E Integration Tests")
        print("=" * 70)
        print()

        # Define test suites
        test_suites = [
            ("Health Check", [
                self.test_health_check,
                self.test_health_check_method_not_allowed,
            ]),
            ("Analyze Page", [
                self.test_analyze_page_basic,
                self.test_analyze_page_empty_items,
                self.test_analyze_page_missing_fields,
                self.test_analyze_page_invalid_bbox,
                self.test_analyze_page_large_payload,
            ]),
            ("Event Logging", [
                self.test_event_requires_auth,
                self.test_event_click_with_auth,
                self.test_event_thumbs_up_with_auth,
                self.test_event_thumbs_down_with_auth,
                self.test_event_missing_fields_with_auth,
            ]),
            ("Activity Tracking", [
                self.test_activity_track_page_visit,
                self.test_activity_track_click,
                self.test_activity_track_missing_timestamp,
                self.test_activity_track_empty_activities,
                self.test_activity_track_batch,
            ]),
            ("Voice Onboarding", [
                self.test_voice_start_session,
                self.test_voice_text_message_first,
                self.test_voice_text_message_with_interests,
                self.test_voice_text_message_end_intent,
                self.test_voice_session_status,
                self.test_voice_session_status_not_found,
                self.test_voice_get_opening_message,
            ]),
            ("Preferences", [
                self.test_preferences_get,
                self.test_preferences_save,
                self.test_preferences_debug_profile,
            ]),
            ("Authentication", [
                self.test_auth_google_redirect,
                self.test_auth_me_unauthenticated,
                self.test_auth_dev_token,
            ]),
            ("Error Handling", [
                self.test_404_endpoint,
                self.test_invalid_json,
                self.test_cors_headers,
            ]),
            ("Fallback Scenarios", [
                self.test_analyze_page_without_auth,
                self.test_voice_text_fallback_when_daily_unavailable,
                self.test_activity_tracking_graceful_degradation,
            ]),
        ]

        total_passed = 0
        total_failed = 0

        for suite_name, tests in test_suites:
            suite = TestSuite(name=suite_name)
            print(f"\n{'─' * 50}")
            print(f"  {suite_name}")
            print(f"{'─' * 50}")

            for test_func in tests:
                test_name = test_func.__name__.replace("test_", "").replace("_", " ").title()
                result = await self.run_test(test_name, test_func())
                suite.results.append(result)

                status = "✅ PASS" if result.passed else "❌ FAIL"
                print(f"  {status} {test_name} ({result.duration_ms:.0f}ms)")
                if result.details:
                    print(f"       └─ {result.details}")
                if result.error:
                    print(f"       └─ Error: {result.error}")

            self.suites.append(suite)
            total_passed += suite.passed
            total_failed += suite.failed

        # Print summary
        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print()

        for suite in self.suites:
            status = "✅" if suite.failed == 0 else "⚠️"
            print(f"  {status} {suite.name}: {suite.passed}/{suite.total} passed")

        print()
        print(f"  {'─' * 40}")
        total = total_passed + total_failed
        pct = (total_passed / total * 100) if total > 0 else 0
        status = "✅ ALL TESTS PASSED" if total_failed == 0 else f"❌ {total_failed} TESTS FAILED"
        print(f"  {status}")
        print(f"  Total: {total_passed}/{total} ({pct:.1f}%)")
        print()

        await self.teardown()

        return total_failed == 0


async def main():
    runner = IntegrationTestRunner()
    success = await runner.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

#!/bin/bash

# ============================================
# InterestLens Backend API Test Commands
# Base URL: http://localhost:8000
# ============================================

BASE_URL="http://localhost:8000"

# Set your JWT token here after OAuth login
JWT_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdHJpbmciLCJlbWFpbCI6InN0cmluZyIsIm5hbWUiOiJzdHJpbmciLCJwaWN0dXJlIjoic3RyaW5nIiwiZXhwIjoxNzcyNTAxMzkxfQ.oJtNjFuOQVUvnO5x0i5Dvb84HzTJwCkOabJql6sWnqk"

# -------------------------------------------
# 1. HEALTH & STATUS ENDPOINTS
# -------------------------------------------

echo "=== Testing Health & Status Endpoints ==="

# Root endpoint - check API is running
echo -e "\n--- Root Endpoint ---"
curl -s -X GET "$BASE_URL/" | jq .

# Health check
echo -e "\n--- Health Check ---"
curl -s -X GET "$BASE_URL/health" | jq .

# -------------------------------------------
# 2. AUTHENTICATION ENDPOINTS
# -------------------------------------------

echo -e "\n=== Testing Authentication Endpoints ==="

# Get current user (requires JWT token)
echo -e "\n--- Get Current User ---"
curl -s -X GET "$BASE_URL/auth/me" \
  -H "Authorization: Bearer $JWT_TOKEN" | jq .

# Logout
#echo -e "\n--- Logout ---"
#curl -s -X POST "$BASE_URL/auth/logout" | jq .

# -------------------------------------------
# 3. PAGE ANALYSIS ENDPOINTS
# -------------------------------------------

echo -e "\n=== Testing Page Analysis Endpoints ==="

# Analyze page (without auth - limited mode)
echo -e "\n--- Analyze Page (No Auth) ---"
curl -s -X POST "$BASE_URL/analyze_page" \
  -H "Content-Type: application/json" \
  -d '{
    "page_url": "https://news.ycombinator.com",
    "dom_outline": {
      "title": "Hacker News",
      "headings": ["Top Stories"],
      "main_text_excerpt": "Tech news and discussions"
    },
    "items": [
      {
        "id": "item_1",
        "href": "https://example.com/article",
        "text": "New AI Model Released",
        "snippet": "A breakthrough in machine learning...",
        "bbox": [10, 20, 300, 100],
        "thumbnail_base64": null
      }
    ]
  }' | jq .

# Analyze page with auth and authenticity check disabled
echo -e "\n--- Analyze Page (With Auth, No Authenticity Check) ---"
curl -s -X POST "$BASE_URL/analyze_page?check_authenticity=false" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "page_url": "https://news.ycombinator.com",
    "dom_outline": {
      "title": "Hacker News",
      "headings": ["Top Stories"],
      "main_text_excerpt": "Tech news"
    },
    "items": [
      {
        "id": "item_1",
        "href": "https://example.com/article",
        "text": "Test Article",
        "snippet": "Test snippet",
        "bbox": [0, 0, 100, 50],
        "thumbnail_base64": null
      }
    ]
  }' | jq .

# Preview URL
echo -e "\n--- Preview URL ---"
curl -s -X POST "$BASE_URL/preview_url?url=https://example.com" \
  -H "Content-Type: application/json" | jq .

# -------------------------------------------
# 4. AUTHENTICITY CHECK ENDPOINTS
# -------------------------------------------

echo -e "\n=== Testing Authenticity Check Endpoints ==="

# Check authenticity with URL only
echo -e "\n--- Check Authenticity (URL only) ---"
curl -s -X POST "$BASE_URL/check_authenticity" \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "test-auth-1",
    "url": "https://apnews.com/article/example",
    "text": "",
    "check_depth": "quick"
  }' | jq .

# Check authenticity with text content
echo -e "\n--- Check Authenticity (with text) ---"
curl -s -X POST "$BASE_URL/check_authenticity" \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "test-auth-2",
    "url": "https://example.com/news",
    "text": "President Biden announced new economic policies today. The White House confirmed the measures during a press briefing.",
    "check_depth": "standard"
  }' | jq .

# Check authenticity - fact-checkable claim
echo -e "\n--- Check Authenticity (fact-checkable claim) ---"
curl -s -X POST "$BASE_URL/check_authenticity" \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "test-auth-3",
    "url": "https://example.com/viral",
    "text": "A viral post claims COVID vaccines contain microchips. Health officials have denied these claims.",
    "check_depth": "standard"
  }' | jq .

# Batch authenticity check
echo -e "\n--- Batch Authenticity Check ---"
curl -s -X POST "$BASE_URL/check_authenticity/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"item_id": "batch-1", "url": "https://reuters.com/article/1", "text": "Test article 1", "check_depth": "quick"},
      {"item_id": "batch-2", "url": "https://apnews.com/article/2", "text": "Test article 2", "check_depth": "quick"}
    ],
    "max_concurrent": 2
  }' | jq .

# -------------------------------------------
# 5. VOICE ONBOARDING ENDPOINTS
# -------------------------------------------

echo -e "\n=== Testing Voice Onboarding Endpoints ==="

# Get opening message for text session
echo -e "\n--- Get Text Session Opening ---"
curl -s -X GET "$BASE_URL/voice/text-session/opening" | jq .

# Start text session with first message
echo -e "\n--- Send Text Message (Start Session) ---"
SESSION_ID="test-session-$(date +%s)"
curl -s -X POST "$BASE_URL/voice/text-message" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"message\": \"Hello, I am interested in technology and AI news.\"
  }" | jq .

# Send follow-up message
echo -e "\n--- Send Text Message (Follow-up) ---"
curl -s -X POST "$BASE_URL/voice/text-message" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"message\": \"I also like science and space exploration topics.\"
  }" | jq .

# Get text session status
echo -e "\n--- Get Text Session Status ---"
curl -s -X GET "$BASE_URL/voice/text-session/$SESSION_ID/status" | jq .

# End text session
echo -e "\n--- End Text Session ---"
curl -s -X POST "$BASE_URL/voice/text-session/$SESSION_ID/end" | jq .

# Get voice preferences (no auth - will use anonymous)
echo -e "\n--- Get Voice Preferences ---"
curl -s -X GET "$BASE_URL/voice/preferences" | jq .

# -------------------------------------------
# 6. DAILY.CO VOICE SESSION (requires DAILY_API_KEY)
# -------------------------------------------

echo -e "\n=== Testing Daily.co Voice Session ==="

# Start voice session (creates Daily room)
echo -e "\n--- Start Voice Session ---"
curl -s -X POST "$BASE_URL/voice/start-session" | jq .

# -------------------------------------------
# 7. WEBSOCKET ENDPOINTS (info only)
# -------------------------------------------

echo -e "\n=== WebSocket Endpoints (Manual Testing) ==="
echo "
WebSocket endpoints available for manual testing:

1. Voice Session Updates:
   ws://localhost:8000/voice/session/{room_name}/updates
   - Receive real-time preference updates during voice onboarding

2. Audio Streaming (Chrome Extension):
   ws://localhost:8000/voice/audio-stream/{session_id}
   - Stream audio from browser for transcription
   - Send: {\"type\": \"start_listening\"}, {\"type\": \"audio_chunk\", \"data\": \"base64\"}, {\"type\": \"stop_listening\"}
   - Receive: {\"type\": \"transcription\", \"text\": \"...\"}, {\"type\": \"agent_response\", \"text\": \"...\"}

Use wscat or browser WebSocket API to test:
  wscat -c ws://localhost:8000/voice/audio-stream/test-session
"

echo -e "\n=== All Tests Complete ==="

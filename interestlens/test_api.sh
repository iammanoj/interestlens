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

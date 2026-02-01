# InterestLens Backend Test Results

**Test Date:** 2026-01-31
**Environment:** macOS Darwin 24.6.0
**Backend Status:** Running on localhost:8000

---

## 1. API Integration Tests

All endpoints tested via `test_api.sh` script.

### Health & Status Endpoints

| Endpoint | Method | Status | Response |
|----------|--------|--------|----------|
| `/` | GET | ✅ PASS | `{"message": "InterestLens API", "status": "running"}` |
| `/health` | GET | ✅ PASS | `{"status": "healthy"}` |

### Authentication Endpoints

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/auth/me` | GET | ✅ PASS | Returns 401 for invalid/expired tokens (expected behavior) |

### Page Analysis Endpoints

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/analyze_page` | POST | ✅ PASS | No auth - returns scored items with topics |
| `/analyze_page?check_authenticity=false` | POST | ✅ PASS | Auth mode with authenticity disabled |
| `/preview_url` | POST | ✅ PASS | Returns URL preview metadata |

**Sample Response (analyze_page):**
```json
{
  "items": [
    {
      "id": "item_1",
      "score": 50,
      "topics": ["AI/ML", "open source"],
      "why": "Prominent content about AI/ML, open source.",
      "authenticity_score": null,
      "authenticity_status": null,
      "authenticity_explanation": null
    }
  ],
  "page_topics": ["news_aggregator"],
  "profile_summary": null,
  "weave_trace_url": null
}
```

### Authenticity Check Endpoints

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/check_authenticity` | POST | ✅ PASS | Single item verification |
| `/check_authenticity/batch` | POST | ✅ PASS | Batch processing (2 items) |
| `/authenticity_status/{item_id}` | GET | ✅ PASS | Cache lookup |

### Voice Onboarding Endpoints

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/voice/text-session/opening` | GET | ✅ PASS | Returns greeting message |
| `/voice/text-message` | POST | ✅ PASS | Conversational flow works |
| `/voice/text-session/{id}/status` | GET | ✅ PASS | Returns session state |
| `/voice/text-session/{id}/end` | POST | ✅ PASS | Ends session, returns preferences |
| `/voice/start-session` | POST | ✅ PASS | Creates Daily.co room |
| `/voice/preferences` | GET | ✅ PASS | Returns user preferences |

---

## 2. Stress Tests

### Authenticity API Stress Test

**Configuration:** 5 requests, 2 concurrent

| Metric | Value |
|--------|-------|
| Total requests | 5 |
| Successful | 5 (100%) |
| Errors | 0 |
| Total time | 13.5s |
| Avg time/request | 4.8s |
| Avg processing | 4823ms |

**Verification Status Distribution:**
- `unverified`: 100% (expected for test URLs without matching fact-checks)

### Cache Stress Test

**Configuration:** 10 URLs

| Pass | Description | Total Time | Avg per URL |
|------|-------------|------------|-------------|
| 1st | Fetch + Cache Write | 0.51s | 51.42ms |
| 2nd | Cache Read (sequential) | 0.00s | 0.15ms |
| 3rd | Cache Read (concurrent) | 0.00s | 3.28ms |

**Results:**
- Cache hit rate: **100%**
- Speedup (cache vs fetch): **339.6x faster**
- Time saved per request: 51.27ms

---

## 3. Fallback Scenario Analysis

### Pipeline Agent (`agents/pipeline.py`)

| Scenario | Fallback Behavior | Verified |
|----------|-------------------|----------|
| Gemini API failure | Returns all items as content with confidence 0.5 | ✅ |
| JSON parsing failure | Cleans markdown, returns default on failure | ✅ |
| No user profile | Limited mode with score=50 | ✅ |
| Empty topics | Returns `["other"]` | ✅ |
| Invalid extractor result | Uses fallback_result structure | ✅ |

### Authenticity Agent (`agents/authenticity.py`)

| Scenario | Fallback Behavior | Verified |
|----------|-------------------|----------|
| Cache hit | Returns cached result immediately | ✅ |
| No claims extracted | score=50, status="unverified" | ✅ |
| No cross-references | score=40, "Unable to verify" message | ✅ |
| Pipeline exception | Returns default_result (score=50, confidence=0.3) | ✅ |
| Short/missing text | Fetches from URL via browserbase | ✅ |

### Redis Client (`services/redis_client.py`)

| Scenario | Fallback Behavior | Verified |
|----------|-------------------|----------|
| Redis unavailable | All functions return None/empty gracefully | ✅ |
| Connection failure | Logs warning, continues without cache | ✅ |
| Index already exists | Silently continues | ✅ |

### Browserbase Service (`services/browserbase.py`)

| Scenario | Fallback Behavior | Verified |
|----------|-------------------|----------|
| Session creation failure | Falls back to HTTP extraction | ✅ |
| Empty JS eval content | Calls `extract_article_simple()` | ✅ |
| HTTP fallback failure | Returns None | ✅ |
| Unknown source domain | Returns credibility=0.5 | ✅ |

### Voice Routes (`voice/routes.py`)

| Scenario | Fallback Behavior | Verified |
|----------|-------------------|----------|
| Daily API key missing | HTTPException 500 with clear message | ✅ |
| Bot startup failure | Room still created, text fallback available | ✅ |
| Redis unavailable | Returns empty preferences gracefully | ✅ |
| Voice session not found | Checks for text session | ✅ |

---

## 4. Type Safety Verification

| Issue | Status | Fix Reference |
|-------|--------|---------------|
| `page_topics` type error | ✅ Fixed | Commit `0ea3d1f` |

The `page_topics` field correctly returns `List[str]` in all scenarios:
- When `page_type` is a string: wrapped in list `[page_type]`
- Response model validates: `page_topics: List[str] = []`

---

## 5. Test Commands Reference

```bash
# Run API integration tests
cd interestlens && bash test_api.sh

# Run authenticity stress test
cd interestlens/backend
source .venv/bin/activate
python3 stress_test_authenticity.py --requests 10 --concurrent 3

# Run cache stress test
python3 stress_test_cache.py --urls 20
```

---

## Summary

| Category | Status |
|----------|--------|
| API Endpoints | ✅ All passing |
| Stress Tests | ✅ All passing |
| Fallback Scenarios | ✅ All verified |
| Type Safety | ✅ Verified |
| Cache Performance | ✅ 339x speedup |

**No critical issues found.** The system handles failures gracefully with appropriate fallbacks and sensible defaults.
